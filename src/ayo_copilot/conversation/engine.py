"""The turn engine: one user message in, one reply out, the case updated atomically.

A turn loads the case, works on an in-memory snapshot (tool handlers change it, so exit
criteria see what the turn accepted so far), calls the model until it answers without
tool calls, and commits everything in one transaction at the end. Nothing is written
before the commit and no transaction is open during model or embedding calls: when a call
fails, the exception propagates and the user can resend the message.

- **Phase hops.** After an accepted `propose_transition` the next call runs under the new
  phase's prompt and tools, so the reply opens the new phase. At most `MAX_PHASE_HOPS`
  per turn; the turn's earlier tool exchange is dropped on a hop (decision 19).
- **Caps.** At most `MAX_TOOL_ROUNDS` model calls; `TURN_TIMEOUT_SECONDS` is checked
  before every call after the first. A capped turn replies with the fallback and still
  commits what was accepted.
- **Retrieval.** Once per phase per turn, in the phases of `RETRIEVAL_PHASES`: at the start
  and after a hop into such a phase, with the query built from the snapshot at that
  moment. A failed embedding lets the turn continue without knowledge (the prompt says
  so); the trace records `retrieval_error`.

Logs and traces carry ids, phases, counts, tool names, tokens and durations, never the
messages, tool arguments, results or retrieved text.
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.conversation.case import CaseSnapshot, Phase, TurnChanges
from ayo_copilot.conversation.context import Knowledge, build_messages, build_system_prompt
from ayo_copilot.conversation.prompt_files import PromptSet
from ayo_copilot.conversation.query import build_query
from ayo_copilot.conversation.reply import compose_reply
from ayo_copilot.conversation.store import TurnCommit, commit_turn, load_snapshot
from ayo_copilot.conversation.tools import ToolOutcome, execute_tool, tools_for_phase
from ayo_copilot.db.conversations import RetrievedTrace, ToolCallTrace, TraceRecord
from ayo_copilot.ingestion.embedding import Embedder, EmbeddingError
from ayo_copilot.llm.provider import LLMProvider
from ayo_copilot.llm.types import LLMResponse, Message
from ayo_copilot.search import search

logger = logging.getLogger(__name__)

# `turn_traces.retrieval_error`: a fixed code, never the error's message.
RETRIEVAL_EMBEDDING_FAILED = "embedding_failed"


class CaseClosed(Exception):
    """The case is closed: it is read-only and takes no new messages."""


@dataclass(frozen=True)
class TurnResult:
    """What a committed turn produced. The reply and the changes are customer content."""

    problem_id: UUID
    reply: str = field(repr=False)
    phase_before: Phase
    phase_after: Phase
    version: int
    turn_no: int
    capped: bool
    changes: TurnChanges = field(repr=False)


@dataclass
class _Retrieval:
    """Every retrieval of a turn: chunks in first-seen order, and whether one failed."""

    retrieved: dict[UUID, RetrievedTrace] = field(default_factory=dict)
    error: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sum_tokens(values: Sequence[int | None]) -> int | None:
    """The sum of the reported counts; None when no call reported one."""
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _sum_cost(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return float(sum(known)) if known else None


class TurnEngine:
    """Runs turns. Thread-safe: it holds no per-turn state (FastAPI runs sync endpoints in
    a thread pool). `now` gives an aware datetime (today is taken in `APP_TIMEZONE`);
    `monotonic` measures the turn for the timeout and the trace."""

    def __init__(
        self,
        pool: ConnectionPool,
        llm: LLMProvider,
        embedder: Embedder,
        settings: Settings,
        prompts: PromptSet,
        *,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pool = pool
        self._llm = llm
        self._embedder = embedder
        self._settings = settings
        self._prompts = prompts
        self._now = now
        self._monotonic = monotonic
        self._timezone = ZoneInfo(settings.app_timezone)

    def today(self) -> date:
        return self._now().astimezone(self._timezone).date()

    def handle_turn(self, problem_id: UUID, user_text: str) -> TurnResult:
        """Run one turn of the case with this user message (already validated by the
        channel) and commit it. Raises `CaseNotFound`, `CaseClosed`, `CaseChanged` (another
        turn committed first: nothing is written) or the provider's `LLMError`."""
        if not user_text.strip():
            raise ValueError("user_text must not be empty")
        settings = self._settings
        started = self._monotonic()
        today = self.today()
        snapshot = load_snapshot(
            self._pool, problem_id, message_limit=settings.context_max_messages
        )
        if snapshot.case.state == "closed":
            raise CaseClosed
        phase_before: Phase = snapshot.case.state
        changes = TurnChanges()
        retrieval = _Retrieval()
        outcomes: list[ToolOutcome] = []
        responses: list[LLMResponse] = []
        texts: list[str | None] = []
        hops = 0
        hopped_from: Phase | None = None
        capped = False

        knowledge = self._retrieve(snapshot, user_text, retrieval)
        base_messages = build_messages(
            snapshot.events, snapshot.case.state, user_text, settings.context_max_messages
        )
        exchange: list[Message] = []
        while True:
            if responses and self._monotonic() - started > settings.turn_timeout_seconds:
                capped = True
                break
            phase: Phase = snapshot.case.state
            response = self._llm.complete(
                system=build_system_prompt(
                    self._prompts,
                    snapshot,
                    today=today,
                    timezone_name=settings.app_timezone,
                    knowledge=knowledge,
                    field_max_chars=settings.field_max_chars,
                    phase_changed_from=hopped_from,
                ),
                messages=[*base_messages, *exchange],
                tools=list(tools_for_phase(phase)),
                model=settings.llm_model_by_phase.get(phase),
            )
            responses.append(response)
            texts.append(response.text)
            if not response.tool_calls:
                break
            exchange.append(
                Message(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            for call in response.tool_calls:
                outcome = execute_tool(
                    snapshot, changes, call, allow_transition=hops < settings.max_phase_hops
                )
                outcomes.append(outcome)
                exchange.append(
                    Message(role="tool", content=outcome.content(), tool_call_id=call.id)
                )
            if snapshot.case.state != phase:
                hops += 1
                hopped_from = phase
                exchange = []
                knowledge = self._retrieve(snapshot, user_text, retrieval)
                base_messages = build_messages(
                    snapshot.events, snapshot.case.state, user_text, settings.context_max_messages
                )
            if len(responses) >= settings.max_tool_rounds:
                capped = True
                break

        reply = compose_reply(texts, capped=capped)
        duration_ms = round((self._monotonic() - started) * 1000)
        trace = _trace(settings, responses, outcomes, retrieval, capped, duration_ms)
        committed = commit_turn(
            self._pool,
            TurnCommit(
                snapshot=snapshot,
                phase_before=phase_before,
                user_message=user_text,
                reply=reply,
                changes=changes,
                trace=trace,
            ),
        )
        logger.info(
            "turn committed problem=%s turn=%d phase=%s->%s llm_calls=%d tools=%s"
            " tokens=%s retrieved=%d retrieval_error=%s capped=%s duration_ms=%d",
            problem_id,
            committed.turn_no,
            phase_before,
            snapshot.case.state,
            trace.llm_calls,
            [o.name if o.ok else f"{o.name}:{o.error_code}" for o in outcomes],
            trace.total_tokens,
            len(trace.retrieved),
            trace.retrieval_error,
            capped,
            duration_ms,
        )
        return TurnResult(
            problem_id=problem_id,
            reply=reply,
            phase_before=phase_before,
            phase_after=snapshot.case.state,
            version=committed.version,
            turn_no=committed.turn_no,
            capped=capped,
            changes=changes,
        )

    def _retrieve(
        self, snapshot: CaseSnapshot, user_text: str, retrieval: _Retrieval
    ) -> Knowledge | None:
        """Knowledge for the case's current phase: None when the phase does not retrieve,
        `failed` when the embedder could not be reached. Database errors propagate."""
        settings = self._settings
        if snapshot.case.state not in settings.retrieval_phases:
            return None
        tenants = list(dict.fromkeys([snapshot.case.tenant, settings.common_tenant]))
        try:
            outcome = search(
                self._pool,
                self._embedder,
                settings,
                query=build_query(snapshot, user_text),
                top_k=settings.retrieval_top_k,
                tenants=tenants,
                min_similarity=settings.retrieval_min_similarity,
            )
        except EmbeddingError:
            logger.warning(
                "retrieval failed problem=%s phase=%s: continuing without knowledge",
                snapshot.case.id,
                snapshot.case.state,
            )
            retrieval.error = RETRIEVAL_EMBEDDING_FAILED
            return Knowledge(failed=True)
        for result in outcome.results:
            retrieval.retrieved.setdefault(
                result.hit.chunk_id,
                RetrievedTrace(
                    chunk_id=result.hit.chunk_id,
                    similarity=result.similarity,
                    doc_id=result.hit.doc_id,
                ),
            )
        return Knowledge(results=tuple(outcome.results))


def _trace(
    settings: Settings,
    responses: Sequence[LLMResponse],
    outcomes: Sequence[ToolOutcome],
    retrieval: _Retrieval,
    capped: bool,
    duration_ms: int,
) -> TraceRecord:
    usages = [response.usage for response in responses]
    models = list(dict.fromkeys(r.model for r in responses if r.model))
    return TraceRecord(
        prompts_version=settings.prompts_version,
        llm_calls=len(responses),
        duration_ms=duration_ms,
        model=",".join(models) or None,
        prompt_tokens=_sum_tokens([u.prompt_tokens for u in usages]),
        completion_tokens=_sum_tokens([u.completion_tokens for u in usages]),
        total_tokens=_sum_tokens([u.total_tokens for u in usages]),
        cost=_sum_cost([u.cost for u in usages]),
        tool_calls=tuple(ToolCallTrace(o.name, o.ok, o.error_code) for o in outcomes),
        retrieved=tuple(retrieval.retrieved.values()),
        retrieval_error=retrieval.error,
        capped=capped,
    )
