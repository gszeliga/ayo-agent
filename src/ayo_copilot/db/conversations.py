"""Hand-written SQL for the conversation engine: cases, their events, actions, channel
links and turn traces.

Every function takes a connection and never commits: `conversation/store.py` owns the
transactions. Content (facts, messages, annotations, actions) is read and written here but
never logged; traces are content-free by construction (`TraceRecord`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from ayo_copilot.conversation.case import Action, ActionStatus, Case, Event, Phase

# Longest tool name kept in a trace (the model may ask for any name; ours are shorter).
TRACE_TOOL_NAME_MAX = 64


@dataclass(frozen=True)
class ToolCallTrace:
    """One tool call of a turn: its name and outcome, never its arguments or result."""

    name: str
    ok: bool
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name[:TRACE_TOOL_NAME_MAX])


@dataclass(frozen=True)
class RetrievedTrace:
    """One retrieved chunk: ids and similarity, never its text."""

    chunk_id: UUID
    similarity: float
    doc_id: str


@dataclass(frozen=True)
class TraceRecord:
    """The content-free metrics of one turn (`turn_traces`, without ids and phases)."""

    prompts_version: str
    llm_calls: int
    duration_ms: int
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    tool_calls: tuple[ToolCallTrace, ...] = ()
    retrieved: tuple[RetrievedTrace, ...] = ()
    retrieval_error: str | None = None
    capped: bool = False


@dataclass(frozen=True)
class LinkedCase:
    problem_id: UUID
    tenant: str


# --- Links and cases -------------------------------------------------------------------


def find_link(
    conn: Connection, channel_type: str, external_channel_id: str, external_thread_id: str
) -> LinkedCase | None:
    row = conn.execute(
        """
        select p.id, p.tenant
        from conversation_links l join problems p on p.id = l.problem_id
        where l.channel_type = %s and l.external_channel_id = %s
          and l.external_thread_id = %s
        """,
        (channel_type, external_channel_id, external_thread_id),
    ).fetchone()
    return LinkedCase(problem_id=row[0], tenant=row[1]) if row else None


def insert_problem(conn: Connection, tenant: str, created_by: str | None) -> UUID:
    row = conn.execute(
        "insert into problems (tenant, created_by) values (%s, %s) returning id",
        (tenant, created_by),
    ).fetchone()
    assert row is not None
    return row[0]


def insert_link(
    conn: Connection,
    problem_id: UUID,
    channel_type: str,
    external_channel_id: str,
    external_thread_id: str,
) -> bool:
    """True if inserted; False if the key already links a case (a concurrent request)."""
    row = conn.execute(
        """
        insert into conversation_links
          (problem_id, channel_type, external_channel_id, external_thread_id)
        values (%s, %s, %s, %s)
        on conflict (channel_type, external_channel_id, external_thread_id) do nothing
        returning id
        """,
        (problem_id, channel_type, external_channel_id, external_thread_id),
    ).fetchone()
    return row is not None


def get_case(conn: Connection, problem_id: UUID) -> Case | None:
    row = conn.execute(
        "select id, tenant, state, what, where_, since, standard, version"
        " from problems where id = %s",
        (problem_id,),
    ).fetchone()
    if row is None:
        return None
    return Case(
        id=row[0],
        tenant=row[1],
        state=row[2],
        what=row[3],
        where_=row[4],
        since=row[5],
        standard=row[6],
        version=row[7],
    )


# --- Events, actions, turns ---------------------------------------------------------------

_EVENT_COLUMNS = "id, role, event_type, content, state_at_time, created_at"


def _event(row: tuple) -> Event:
    return Event(
        role=row[1],
        event_type=row[2],
        content=row[3],
        state_at_time=row[4],
        id=row[0],
        created_at=row[5],
    )


def list_annotations(conn: Connection, problem_id: UUID) -> list[Event]:
    """Every event but messages, oldest first."""
    rows = conn.execute(
        f"select {_EVENT_COLUMNS} from problem_events"
        " where problem_id = %s and event_type <> 'message' order by id",
        (problem_id,),
    ).fetchall()
    return [_event(row) for row in rows]


def list_messages(conn: Connection, problem_id: UUID, *, last: int | None = None) -> list[Event]:
    """Messages oldest first: all of them, or only the `last` ones."""
    if last is None:
        rows = conn.execute(
            f"select {_EVENT_COLUMNS} from problem_events"
            " where problem_id = %s and event_type = 'message' order by id",
            (problem_id,),
        ).fetchall()
        return [_event(row) for row in rows]
    rows = conn.execute(
        f"select {_EVENT_COLUMNS} from problem_events"
        " where problem_id = %s and event_type = 'message' order by id desc limit %s",
        (problem_id, last),
    ).fetchall()
    return [_event(row) for row in reversed(rows)]


def list_actions(conn: Connection, problem_id: UUID) -> list[Action]:
    rows = conn.execute(
        "select id, description, owner, due_date, status from actions"
        " where problem_id = %s order by id",
        (problem_id,),
    ).fetchall()
    return [
        Action(description=row[1], owner=row[2], due_date=row[3], status=row[4], id=row[0])
        for row in rows
    ]


def count_turns(conn: Connection, problem_id: UUID) -> int:
    row = conn.execute(
        "select count(*) from turn_traces where problem_id = %s", (problem_id,)
    ).fetchone()
    assert row is not None
    return row[0]


# --- Committing a turn ----------------------------------------------------------------------


def update_problem(conn: Connection, case: Case, *, expected_version: int) -> int | None:
    """Write the case's state and facts and bump its version, only if the stored version
    is still `expected_version`; the new version, or None if it changed meanwhile. Locks
    the row until the transaction ends. `closed_at` is set when the case becomes closed."""
    row = conn.execute(
        """
        update problems set
          state = %(state)s,
          what = %(what)s, where_ = %(where_)s, since = %(since)s, standard = %(standard)s,
          version = version + 1,
          updated_at = now(),
          closed_at = case when %(state)s = 'closed' then coalesce(closed_at, now())
                      else closed_at end
        where id = %(id)s and version = %(version)s
        returning version
        """,
        {
            "id": case.id,
            "state": case.state,
            "what": case.what,
            "where_": case.where_,
            "since": case.since,
            "standard": case.standard,
            "version": expected_version,
        },
    ).fetchone()
    return row[0] if row else None


def insert_events(conn: Connection, problem_id: UUID, events: Sequence[Event]) -> None:
    """Insert in the given order (ids follow it)."""
    with conn.cursor() as cur:
        cur.executemany(
            "insert into problem_events (problem_id, role, content, event_type, state_at_time)"
            " values (%s, %s, %s, %s, %s)",
            [(problem_id, e.role, e.content, e.event_type, e.state_at_time) for e in events],
        )


def insert_actions(conn: Connection, problem_id: UUID, actions: Sequence[Action]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "insert into actions (problem_id, description, owner, due_date, status)"
            " values (%s, %s, %s, %s, %s)",
            [(problem_id, a.description, a.owner, a.due_date, a.status) for a in actions],
        )


def update_action_statuses(
    conn: Connection, problem_id: UUID, updates: Mapping[int, ActionStatus]
) -> int:
    """Set each action's status; only actions of this case are touched. The count updated."""
    updated = 0
    for action_id, status in updates.items():
        cur = conn.execute(
            "update actions set status = %s, updated_at = now() where id = %s and problem_id = %s",
            (status, action_id, problem_id),
        )
        updated += cur.rowcount
    return updated


def insert_trace(
    conn: Connection,
    problem_id: UUID,
    trace: TraceRecord,
    *,
    phase_before: Phase,
    phase_after: Phase,
) -> int:
    """Insert the turn's trace with the next turn number, which it returns. Call it after
    `update_problem`: that row lock makes the numbering safe."""
    row = conn.execute(
        """
        insert into turn_traces (
          problem_id, turn_no, phase_before, phase_after, model, prompts_version, llm_calls,
          prompt_tokens, completion_tokens, total_tokens, cost, tool_calls, retrieved,
          retrieval_error, capped, duration_ms)
        select %(problem_id)s, coalesce(max(turn_no), 0) + 1, %(phase_before)s,
          %(phase_after)s, %(model)s, %(prompts_version)s, %(llm_calls)s, %(prompt_tokens)s,
          %(completion_tokens)s, %(total_tokens)s, %(cost)s, %(tool_calls)s, %(retrieved)s,
          %(retrieval_error)s, %(capped)s, %(duration_ms)s
        from turn_traces where problem_id = %(problem_id)s
        returning turn_no
        """,
        {
            "problem_id": problem_id,
            "phase_before": phase_before,
            "phase_after": phase_after,
            "model": trace.model,
            "prompts_version": trace.prompts_version,
            "llm_calls": trace.llm_calls,
            "prompt_tokens": trace.prompt_tokens,
            "completion_tokens": trace.completion_tokens,
            "total_tokens": trace.total_tokens,
            "cost": trace.cost,
            "tool_calls": Jsonb(
                [{"name": t.name, "ok": t.ok, "error_code": t.error_code} for t in trace.tool_calls]
            ),
            "retrieved": Jsonb(
                [
                    {"chunk_id": str(r.chunk_id), "similarity": r.similarity, "doc_id": r.doc_id}
                    for r in trace.retrieved
                ]
            ),
            "retrieval_error": trace.retrieval_error,
            "capped": trace.capped,
            "duration_ms": trace.duration_ms,
        },
    ).fetchone()
    assert row is not None
    return row[0]
