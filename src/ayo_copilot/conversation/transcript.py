"""A readable Markdown transcript of one session, built from what the database holds: the
session view (messages, annotations, actions, facts) and the turn traces.

It holds conversation content, so it is only ever written to a local, git-ignored file
(`eval/conversations/`) for a person to read; never logged. It works for any session
however it was held: the live test, or a conversation by hand with curl.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ayo_copilot.conversation.case import Event
from ayo_copilot.conversation.store import SessionView
from ayo_copilot.db.conversations import StoredTrace

DEFAULT_OUT = Path("eval/conversations")


@dataclass(frozen=True)
class _Turn:
    user: Event
    reply: Event
    annotations: tuple[Event, ...]
    stored: StoredTrace


def render_transcript(
    session_id: UUID, view: SessionView, traces: Sequence[StoredTrace], *, written_at: datetime
) -> str:
    """The transcript: a header with totals, one section per turn, the final case."""
    turns = _turns(view, traces)
    lines = [f"# Conversation {session_id}", "", *_header(view, traces, written_at), ""]
    for turn in turns:
        lines += [*_turn(turn), ""]
    lines += _final_case(view)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_transcript(
    text: str, *, session_id: UUID, out_dir: Path = DEFAULT_OUT, now: datetime
) -> Path:
    """Write `text` to `<out_dir>/<UTC timestamp>-<session prefix>.md` (never overwrites)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stem}-{str(session_id)[:8]}.md"
    with path.open("x", encoding="utf-8") as file:
        file.write(text)
    return path


# --- Parts --------------------------------------------------------------------------------


def _turns(view: SessionView, traces: Sequence[StoredTrace]) -> list[_Turn]:
    """Pair each turn's user message and reply with its trace. A turn commits its user
    message, then its annotations, then its reply, so an annotation belongs to the turn
    whose messages enclose its id."""
    messages = view.messages
    pairs = list(zip(messages[0::2], messages[1::2], strict=False))
    if (
        len(messages) != 2 * len(traces)
        or any(u.role != "user" or r.role != "assistant" for u, r in pairs)
        or [t.turn_no for t in traces] != list(range(1, len(traces) + 1))
    ):
        raise ValueError(
            f"session has {len(messages)} messages and {len(traces)} traces:"
            " expected a user message and a reply per traced turn"
        )
    turns = []
    for (user, reply), stored in zip(pairs, traces, strict=True):
        assert user.id is not None and reply.id is not None
        inside = tuple(e for e in view.events if e.id is not None and user.id < e.id < reply.id)
        turns.append(_Turn(user, reply, inside, stored))
    return turns


def _header(view: SessionView, traces: Sequence[StoredTrace], written_at: datetime) -> list[str]:
    records = [s.trace for s in traces]
    models = list(dict.fromkeys(m for r in records for m in (r.model or "").split(",") if m))
    versions = list(dict.fromkeys(r.prompts_version for r in records))
    path = " → ".join(_phase_path(traces)) or view.phase
    tokens = _tokens(
        [r.prompt_tokens for r in records],
        [r.completion_tokens for r in records],
        [r.total_tokens for r in records],
    )
    return [
        f"- Written: {written_at.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- Tenant: {view.tenant}",
        f"- Phases: {path} (now {view.phase})",
        f"- Models: {', '.join(models) or 'n/a'}",
        f"- Prompts version: {', '.join(versions) or 'n/a'}",
        f"- Turns: {len(records)} · model calls: {sum(r.llm_calls for r in records)}"
        f" · {tokens}"
        f" · cost: {_cost([r.cost for r in records])}"
        f" · duration: {sum(r.duration_ms for r in records) / 1000:.1f} s",
        f"- Capped turns: {sum(r.capped for r in records)}"
        f" · refused tool calls: {sum(not t.ok for r in records for t in r.tool_calls)}"
        f" · retrieval errors: {sum(r.retrieval_error is not None for r in records)}",
    ]


def _phase_path(traces: Sequence[StoredTrace]) -> list[str]:
    path: list[str] = []
    for stored in traces:
        for phase in (stored.phase_before, stored.phase_after):
            if not path or path[-1] != phase:
                path.append(phase)
    return path


def _turn(turn: _Turn) -> list[str]:
    stored, trace = turn.stored, turn.stored.trace
    phases = (
        stored.phase_before
        if stored.phase_before == stored.phase_after
        else f"{stored.phase_before} → {stored.phase_after}"
    )
    tools = ", ".join(
        f"{t.name} ok" if t.ok else f"{t.name} refused ({t.error_code})" for t in trace.tool_calls
    )
    metrics = [
        f"calls {trace.llm_calls}",
        _tokens([trace.prompt_tokens], [trace.completion_tokens], [trace.total_tokens]),
        f"cost {_cost([trace.cost])}",
        f"{trace.duration_ms} ms",
        f"retrieved {len(trace.retrieved)}",
    ]
    if trace.retrieval_error:
        metrics.append(f"retrieval error: {trace.retrieval_error}")
    if trace.capped:
        metrics.append("CAPPED")
    lines = [
        f"## Turn {stored.turn_no} · {phases}",
        "",
        "**User**",
        "",
        *_quote(turn.user.content),
        "",
        "**Copilot**",
        "",
        *_quote(turn.reply.content),
        "",
        f"- Tools: {tools or 'none'}",
    ]
    for event in turn.annotations:
        lines.append(f"- Recorded {event.event_type}: {_one_line(event.content)}")
    lines.append(f"- {' · '.join(metrics)}")
    return lines


def _final_case(view: SessionView) -> list[str]:
    lines = ["## Final case", "", f"Phase: {view.phase} · version {view.version}", ""]
    lines += ["| Fact | Value |", "|---|---|"]
    lines += [f"| {name} | {_cell(value)} |" for name, value in view.fields.items()]
    lines += ["", "Annotations:", ""]
    lines += [
        f"- [{e.state_at_time}] {e.event_type}: {_one_line(e.content)}" for e in view.events
    ] or ["- none"]
    lines += ["", "Actions:", ""]
    lines += [
        f"- [{a.action.id}] {_one_line(a.action.description)} · owner: {a.action.owner}"
        f" · due {a.action.due_date.isoformat()} · {a.action.status}"
        + (" · OVERDUE" if a.overdue else "")
        for a in view.actions
    ] or ["- none"]
    return lines


# --- Formatting ---------------------------------------------------------------------------


def _quote(text: str) -> list[str]:
    return [f"> {line}".rstrip() for line in text.splitlines()] or [">"]


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _cell(value: str | None) -> str:
    return _one_line(value).replace("|", "\\|") if value and value.strip() else "(not recorded)"


def _tokens(
    prompt: Sequence[int | None], completion: Sequence[int | None], total: Sequence[int | None]
) -> str:
    if all(t is None for t in total):
        return "tokens n/a"
    return (
        f"tokens {sum(t or 0 for t in total)}"
        f" ({sum(t or 0 for t in prompt)} in / {sum(t or 0 for t in completion)} out)"
    )


def _cost(costs: Sequence[float | None]) -> str:
    if all(c is None for c in costs):
        return "n/a"
    return f"{sum(c or 0.0 for c in costs):.6f}"
