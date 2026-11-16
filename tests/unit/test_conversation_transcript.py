"""The session transcript: turns paired with their traces, annotations attributed to their
turn, metrics and totals, the final case, and the file it is written to."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ayo_copilot.conversation.case import Action, Event
from ayo_copilot.conversation.store import SessionAction, SessionView
from ayo_copilot.conversation.transcript import render_transcript, write_transcript
from ayo_copilot.db.conversations import RetrievedTrace, StoredTrace, ToolCallTrace, TraceRecord

SESSION = UUID("3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b")
NOW = datetime(2026, 11, 16, 9, 30, 5, tzinfo=UTC)


def message(event_id: int, role: str, text: str, phase: str) -> Event:
    return Event(role, "message", text, phase, id=event_id)  # type: ignore[arg-type]


def annotation(event_id: int, event_type: str, text: str, phase: str) -> Event:
    return Event("assistant", event_type, text, phase, id=event_id)  # type: ignore[arg-type]


def stored(turn_no: int, before: str, after: str, **trace: object) -> StoredTrace:
    trace.setdefault("prompts_version", "draft-1")
    trace.setdefault("llm_calls", 1)
    trace.setdefault("duration_ms", 1200)
    return StoredTrace(turn_no, before, after, NOW, TraceRecord(**trace))  # type: ignore[arg-type]


def view(messages: list[Event], events: list[Event], actions=(), phase="challenge") -> SessionView:
    return SessionView(
        problem_id=uuid4(),
        tenant="cliente-acme",
        phase=phase,  # type: ignore[arg-type]
        version=len(messages) // 2,
        turns=len(messages) // 2,
        fields={
            "what": "Merma del 4 %",
            "where": "Línea 2 | llenadora",
            "since": None,
            "standard": " ",
        },
        events=events,
        actions=list(actions),
        messages=messages,
    )


MESSAGES = [
    message(1, "user", "Tenemos merma", "understand"),
    message(2, "assistant", "¿Dónde?\nY ¿desde cuándo?", "understand"),
    message(3, "user", "Línea 2", "understand"),
    message(6, "assistant", "Anotado.", "challenge"),
]
EVENTS = [
    annotation(4, "evidence", "El sensor   marca\n3 mm de más", "understand"),
    annotation(5, "hypothesis", "Sensor descalibrado", "understand"),
]
TRACES = [
    stored(
        1,
        "understand",
        "understand",
        model="m/one",
        prompt_tokens=1000,
        completion_tokens=50,
        total_tokens=1050,
        cost=0.0001,
    ),
    stored(
        2,
        "understand",
        "challenge",
        model="m/one,m/two",
        llm_calls=2,
        prompt_tokens=2000,
        completion_tokens=100,
        total_tokens=2100,
        cost=0.0002,
        duration_ms=2300,
        tool_calls=(
            ToolCallTrace("record_field", True),
            ToolCallTrace("propose_transition", False, "criteria_not_met"),
        ),
        retrieved=(RetrievedTrace(uuid4(), 0.81, "upload-1"),),
        retrieval_error="embedding_failed",
        capped=True,
    ),
]


def test_header_has_the_totals_and_the_phase_path() -> None:
    text = render_transcript(SESSION, view(MESSAGES, EVENTS), TRACES, written_at=NOW)

    assert text.startswith(f"# Conversation {SESSION}\n")
    assert "- Written: 2026-11-16T09:30:05Z" in text
    assert "- Phases: understand → challenge (now challenge)" in text
    assert "- Models: m/one, m/two" in text
    assert "- Prompts version: draft-1" in text
    assert (
        "- Turns: 2 · model calls: 3 · tokens 3150 (3000 in / 150 out) · cost: 0.000300"
        " · duration: 3.5 s"
    ) in text
    assert "- Capped turns: 1 · refused tool calls: 1 · retrieval errors: 1" in text


def test_each_turn_has_its_messages_tools_annotations_and_metrics() -> None:
    text = render_transcript(SESSION, view(MESSAGES, EVENTS), TRACES, written_at=NOW)
    first, second = text.split("## Turn ")[1:3]

    assert first.startswith("1 · understand\n")
    assert "> Tenemos merma" in first
    assert "> ¿Dónde?\n> Y ¿desde cuándo?" in first
    assert "- Tools: none" in first
    assert "Recorded" not in first
    assert (
        "- calls 1 · tokens 1050 (1000 in / 50 out) · cost 0.000100 · 1200 ms · retrieved 0"
        in first
    )

    assert second.startswith("2 · understand → challenge\n")
    assert "- Tools: record_field ok, propose_transition refused (criteria_not_met)" in second
    assert "- Recorded evidence: El sensor marca 3 mm de más" in second
    assert "- Recorded hypothesis: Sensor descalibrado" in second
    assert "retrieved 1 · retrieval error: embedding_failed · CAPPED" in second


def test_final_case_lists_facts_annotations_and_actions() -> None:
    action = Action("Recalibrar el sensor", "Ana", date(2026, 11, 20), "pending", id=7)
    text = render_transcript(
        SESSION,
        view(MESSAGES, EVENTS, [SessionAction(action, overdue=True)]),
        TRACES,
        written_at=NOW,
    )
    final = text[text.index("## Final case") :]

    assert "| what | Merma del 4 % |" in final
    assert "| where | Línea 2 \\| llenadora |" in final
    assert "| since | (not recorded) |" in final and "| standard | (not recorded) |" in final
    assert "- [understand] evidence: El sensor marca 3 mm de más" in final
    assert "- [7] Recalibrar el sensor · owner: Ana · due 2026-11-20 · pending · OVERDUE" in final


def test_no_usage_reads_as_not_available() -> None:
    traces = [stored(1, "understand", "understand"), stored(2, "understand", "challenge")]

    text = render_transcript(SESSION, view(MESSAGES, []), traces, written_at=NOW)

    assert "tokens n/a · cost: n/a" in text
    assert "- Models: n/a" in text


def test_an_empty_session_renders_its_case_only() -> None:
    text = render_transcript(SESSION, view([], [], phase="understand"), [], written_at=NOW)

    assert "## Turn" not in text
    assert "- Phases: understand (now understand)" in text
    assert "Annotations:\n\n- none" in text and "Actions:\n\n- none" in text


@pytest.mark.parametrize(
    ("messages", "traces"),
    [
        (MESSAGES[:3], TRACES),  # a reply missing
        (MESSAGES, TRACES[:1]),  # a trace missing
        ([MESSAGES[1], MESSAGES[0], *MESSAGES[2:]], TRACES),  # out of order
    ],
    ids=["reply missing", "trace missing", "roles swapped"],
)
def test_inconsistent_sessions_are_refused(messages: list[Event], traces: list) -> None:
    with pytest.raises(ValueError, match="expected a user message and a reply"):
        render_transcript(SESSION, view(messages, []), traces, written_at=NOW)


def test_written_under_a_timestamped_name_and_never_overwritten(tmp_path: Path) -> None:
    out = tmp_path / "conversations"

    path = write_transcript("# x\n", session_id=SESSION, out_dir=out, now=NOW)

    assert path == out / "20261116T093005Z-3f2b8c1e.md"
    assert path.read_text() == "# x\n"
    with pytest.raises(FileExistsError):
        write_transcript("# y\n", session_id=SESSION, out_dir=out, now=NOW)
    assert path.read_text() == "# x\n"
