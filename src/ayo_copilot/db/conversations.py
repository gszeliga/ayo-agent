"""Hand-written SQL for the conversation engine: cases, their events, actions, channel
links and turn traces.

Every function takes a connection and never commits: `conversation/store.py` owns the
transactions. Content (facts, messages, annotations, actions) is read and written here but
never logged; traces are content-free by construction (`TraceRecord`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from ayo_copilot.conversation.case import PHASES, Action, ActionStatus, Case, Event, Phase
from ayo_copilot.db.repository import escape_like

# Longest tool name kept in a trace (the model may ask for any name; ours are shorter).
TRACE_TOOL_NAME_MAX = 64


@dataclass(frozen=True)
class ToolCallTrace:
    """One tool call of a turn: its name and outcome, never its arguments or result."""

    name: str
    ok: bool
    error_code: str | None = None
    # `propose_transition` only: the phase proposed (None when its arguments were invalid,
    # and in traces written before it was recorded) and the missing item codes.
    target: Phase | None = None
    missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name[:TRACE_TOOL_NAME_MAX])

    def as_json(self) -> dict[str, object]:
        data: dict[str, object] = {"name": self.name, "ok": self.ok, "error_code": self.error_code}
        if self.target is not None:
            data["target"] = self.target
            data["missing"] = list(self.missing)
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ToolCallTrace":
        """Read back a stored call; older rows lack `target` and `missing`, and a value
        that is not a known phase reads as None."""
        target = data.get("target")
        missing = data.get("missing") or []
        return cls(
            data["name"],
            data["ok"],
            data.get("error_code"),
            target=target if target in PHASES else None,
            missing=tuple(str(item) for item in missing) if target in PHASES else (),
        )


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
class StoredTrace:
    """A committed turn's trace as read back: its number, phases and time, and the
    metrics."""

    turn_no: int
    phase_before: Phase
    phase_after: Phase
    created_at: datetime
    trace: TraceRecord


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
            "tool_calls": Jsonb([t.as_json() for t in trace.tool_calls]),
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


# --- Reading traces ---------------------------------------------------------------------


_TRACE_SELECT = """
    select turn_no, phase_before, phase_after, created_at, model, prompts_version,
      llm_calls, prompt_tokens, completion_tokens, total_tokens, cost, tool_calls,
      retrieved, retrieval_error, capped, duration_ms
    from turn_traces where problem_id = %(problem_id)s order by turn_no"""


def _stored_trace(row: tuple) -> StoredTrace:
    return StoredTrace(
        turn_no=row[0],
        phase_before=row[1],
        phase_after=row[2],
        created_at=row[3],
        trace=TraceRecord(
            model=row[4],
            prompts_version=row[5],
            llm_calls=row[6],
            prompt_tokens=row[7],
            completion_tokens=row[8],
            total_tokens=row[9],
            cost=None if row[10] is None else float(row[10]),
            tool_calls=tuple(ToolCallTrace.from_json(t) for t in row[11]),
            retrieved=tuple(
                RetrievedTrace(UUID(r["chunk_id"]), r["similarity"], r["doc_id"]) for r in row[12]
            ),
            retrieval_error=row[13],
            capped=row[14],
            duration_ms=row[15],
        ),
    )


def list_traces(conn: Connection, problem_id: UUID) -> list[StoredTrace]:
    """A case's turn traces, in turn order."""
    rows = conn.execute(_TRACE_SELECT, {"problem_id": problem_id}).fetchall()
    return [_stored_trace(row) for row in rows]


def list_trace_page(
    conn: Connection, problem_id: UUID, *, limit: int, offset: int
) -> list[StoredTrace]:
    """A window of a case's turn traces, oldest first: turns `offset + 1` onwards."""
    rows = conn.execute(
        f"{_TRACE_SELECT} limit %(limit)s offset %(offset)s",
        {"problem_id": problem_id, "limit": limit, "offset": offset},
    ).fetchall()
    return [_stored_trace(row) for row in rows]


def list_turn_messages(
    conn: Connection, problem_id: UUID, *, first_turn: int, last_turn: int
) -> dict[tuple[int, str], Event]:
    """The messages of turns `first_turn` to `last_turn`, keyed by (turn, role).

    Every committed turn stores exactly one user message and one reply (`commit_turn`), so
    the n-th message of each role belongs to turn n.
    """
    rows = conn.execute(
        f"""
        select turn, {_EVENT_COLUMNS} from (
          select row_number() over (partition by role order by id) as turn, {_EVENT_COLUMNS}
          from problem_events where problem_id = %(problem_id)s and event_type = 'message'
        ) numbered
        where turn between %(first)s and %(last)s
        """,
        {"problem_id": problem_id, "first": first_turn, "last": last_turn},
    ).fetchall()
    return {(row[0], row[2]): _event(row[1:]) for row in rows}


def document_titles(conn: Connection, tenant: str, doc_ids: Sequence[str]) -> dict[str, str | None]:
    """The titles of the tenant's documents among `doc_ids` (a title may be null); a
    document missing from the result no longer exists."""
    if not doc_ids:
        return {}
    rows = conn.execute(
        "select doc_id, title from documents where tenant = %s and doc_id = any(%s)",
        (tenant, list(doc_ids)),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def chunk_indexes(
    conn: Connection, tenant: str, chunk_ids: Sequence[UUID]
) -> dict[UUID, tuple[str, int]]:
    """Where the tenant's chunks among `chunk_ids` are now: `chunk_id` -> (`doc_id`,
    `chunk_index`). A chunk missing from the result is no longer stored: reprocessing or
    replacing a document replaces its chunks (new ids), and deleting it removes them."""
    if not chunk_ids:
        return {}
    rows = conn.execute(
        """
        select c.id, d.doc_id, c.chunk_index
        from chunks c join documents d on d.id = c.document_id
        where c.id = any(%s) and d.tenant = %s
        """,
        (list(chunk_ids), tenant),
    ).fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


# --- Listing cases (admin)-------------------------------------------------------------------


@dataclass(frozen=True)
class CaseRow:
    """One case of the admin listing: ids, phase, counts and times; `what` is content."""

    id: UUID
    tenant: str
    state: Phase
    what: str | None
    turns: int
    pending_actions: int
    overdue_actions: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    # The web thread linked to the case, if any (the earliest such link).
    web_session_id: str | None

    def __repr__(self) -> str:
        return f"CaseRow(id={self.id}, tenant={self.tenant!r}, state={self.state!r})"


# The columns of `CaseRow`, in order; `%(today)s` decides what is overdue.
_CASE_ROW_SELECT = """
    select p.id, p.tenant, p.state, p.what,
      (select count(*) from turn_traces t where t.problem_id = p.id),
      (select count(*) from actions a where a.problem_id = p.id and a.status = 'pending'),
      (select count(*) from actions a
        where a.problem_id = p.id and a.status = 'pending' and a.due_date < %(today)s),
      p.created_at, p.updated_at, p.closed_at,
      (select l.external_thread_id from conversation_links l
        where l.problem_id = p.id and l.channel_type = 'web'
        order by l.created_at, l.id limit 1)
    from problems p"""


def list_cases(
    conn: Connection,
    *,
    today: date,
    tenant: str | None = None,
    phase: Phase | None = None,
    closed: bool | None = None,
    q: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[CaseRow], int]:
    """One page of cases, newest update first (ties by id, so pages are stable), and the
    number matching the filters. `q` is a case-insensitive substring of `what`, matched
    literally; overdue means pending with a due date before `today`."""
    conditions: list[str] = []
    params: dict[str, object] = {"today": today, "limit": limit, "offset": offset}
    if tenant is not None:
        conditions.append("p.tenant = %(tenant)s")
        params["tenant"] = tenant
    if phase is not None:
        conditions.append("p.state = %(phase)s")
        params["phase"] = phase
    if closed is not None:
        conditions.append("p.state = 'closed'" if closed else "p.state <> 'closed'")
    if q:
        conditions.append("p.what ilike %(pattern)s escape '\\'")
        params["pattern"] = f"%{escape_like(q)}%"
    where = f"where {' and '.join(conditions)}" if conditions else ""
    total_row = conn.execute(f"select count(*) from problems p {where}", params).fetchone()
    assert total_row is not None
    rows = conn.execute(
        f"""
        {_CASE_ROW_SELECT} {where}
        order by p.updated_at desc, p.id
        limit %(limit)s offset %(offset)s
        """,
        params,
    ).fetchall()
    return [CaseRow(*row) for row in rows], total_row[0]


def get_case_row(conn: Connection, problem_id: UUID, *, today: date) -> CaseRow | None:
    """One case as `list_cases` shows it (same counts and web link); None if unknown."""
    row = conn.execute(
        f"{_CASE_ROW_SELECT} where p.id = %(id)s", {"id": problem_id, "today": today}
    ).fetchone()
    return None if row is None else CaseRow(*row)


def delete_case(conn: Connection, problem_id: UUID) -> tuple[str, int] | None:
    """Delete a case; its events, actions, links and traces go with it (`on delete
    cascade`). Returns its tenant and turn count, or None if there is no such case."""
    row = conn.execute(
        "delete from problems p where p.id = %s returning p.tenant,"
        " (select count(*) from turn_traces t where t.problem_id = p.id)",
        (problem_id,),
    ).fetchone()
    return None if row is None else (row[0], row[1])


# --- Case summaries ------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryRecord:
    """An AI summary of a case and how it was made. `content` is customer content."""

    content: str = field(repr=False)
    source_version: int
    model: str
    prompts_version: str
    total_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True)
class StoredSummary:
    """A stored summary and when it was generated."""

    summary: SummaryRecord
    created_at: datetime


def get_case_summary(conn: Connection, problem_id: UUID) -> StoredSummary | None:
    row = conn.execute(
        "select content, source_version, model, prompts_version, total_tokens, cost,"
        " created_at from case_summaries where problem_id = %s",
        (problem_id,),
    ).fetchone()
    if row is None:
        return None
    return StoredSummary(
        summary=SummaryRecord(
            content=row[0],
            source_version=row[1],
            model=row[2],
            prompts_version=row[3],
            total_tokens=row[4],
            cost=None if row[5] is None else float(row[5]),
        ),
        created_at=row[6],
    )


def upsert_case_summary(conn: Connection, problem_id: UUID, summary: SummaryRecord) -> bool:
    """Store the case's summary, replacing the previous one unless that one was generated
    from a newer case version (two generations racing: the one that saw the later case
    wins). Never touches `problems`. Returns whether it was stored."""
    row = conn.execute(
        """
        insert into case_summaries (problem_id, content, source_version, model,
          prompts_version, total_tokens, cost)
        values (%(problem_id)s, %(content)s, %(source_version)s, %(model)s,
          %(prompts_version)s, %(total_tokens)s, %(cost)s)
        on conflict (problem_id) do update set
          content = excluded.content,
          source_version = excluded.source_version,
          model = excluded.model,
          prompts_version = excluded.prompts_version,
          total_tokens = excluded.total_tokens,
          cost = excluded.cost,
          created_at = excluded.created_at
        where case_summaries.source_version <= excluded.source_version
        returning 1
        """,
        {
            "problem_id": problem_id,
            "content": summary.content,
            "source_version": summary.source_version,
            "model": summary.model,
            "prompts_version": summary.prompts_version,
            "total_tokens": summary.total_tokens,
            "cost": summary.cost,
        },
    ).fetchone()
    return row is not None
