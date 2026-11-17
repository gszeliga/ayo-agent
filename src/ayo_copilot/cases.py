"""Admin operations on the copilot's cases (every channel). These functions own the
transactions; the SQL lives in `db/conversations.py`."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from psycopg_pool import ConnectionPool

from ayo_copilot.conversation.case import Case, CaseSnapshot, Event, Phase
from ayo_copilot.conversation.store import SessionAction
from ayo_copilot.db import conversations as db
from ayo_copilot.db.conversations import CaseRow, StoredSummary, StoredTrace, SummaryRecord


@dataclass(frozen=True)
class CaseDetail:
    """One case for the admin view: its listing row, the facts and version, the
    annotations, the actions (with `overdue`) and the AI summary, if any. Messages and
    traces are paged apart."""

    row: CaseRow
    case: Case
    events: list[Event]
    actions: list[SessionAction]
    summary: StoredSummary | None


def read_case_page(
    pool: ConnectionPool,
    *,
    today: date,
    tenant: str | None = None,
    phase: Phase | None = None,
    closed: bool | None = None,
    q: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[CaseRow], int]:
    """One page of cases and the total matching the filters.

    Repeatable read: the page and the count are two statements, and a turn committed
    between them could otherwise make `total` disagree with the items.
    """
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        return db.list_cases(
            conn,
            today=today,
            tenant=tenant,
            phase=phase,
            closed=closed,
            q=q,
            limit=limit,
            offset=offset,
        )


def read_case_detail(pool: ConnectionPool, case_id: UUID, *, today: date) -> CaseDetail | None:
    """A case with its facts, annotations, actions and summary; None if there is no such
    case.

    Repeatable read, so the counts in the row agree with the actions and the version.
    """
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        row = db.get_case_row(conn, case_id, today=today)
        if row is None:
            return None
        case = db.get_case(conn, case_id)
        assert case is not None
        events = db.list_annotations(conn, case_id)
        actions = db.list_actions(conn, case_id)
        summary = db.get_case_summary(conn, case_id)
    return CaseDetail(
        row=row,
        case=case,
        events=events,
        actions=[SessionAction(action, action.is_overdue(today)) for action in actions],
        summary=summary,
    )


@dataclass(frozen=True)
class CaseTurn:
    """One committed turn: its trace and its two messages (customer content)."""

    trace: StoredTrace
    user_message: Event
    reply: Event


@dataclass(frozen=True)
class CaseTurns:
    """A page of a case's turns, oldest first, and the titles of the documents they
    retrieved (`doc_id` -> title; a missing `doc_id` is a deleted document)."""

    turns: list[CaseTurn]
    total: int
    document_titles: dict[str, str | None]


class MissingTurnMessage(Exception):
    """A committed turn without its user message or reply: `commit_turn` writes both, so
    this is a broken invariant, not a client error."""


def read_case_turns(
    pool: ConnectionPool, case_id: UUID, *, limit: int, offset: int
) -> CaseTurns | None:
    """Turns `offset + 1` to `offset + limit` of a case, oldest first, with their messages;
    None if there is no such case.

    Repeatable read, so the traces, the messages, the titles and `total` agree.
    """
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        case = db.get_case(conn, case_id)
        if case is None:
            return None
        total = db.count_turns(conn, case_id)
        traces = db.list_trace_page(conn, case_id, limit=limit, offset=offset)
        messages = (
            db.list_turn_messages(
                conn, case_id, first_turn=traces[0].turn_no, last_turn=traces[-1].turn_no
            )
            if traces
            else {}
        )
        doc_ids = sorted({r.doc_id for t in traces for r in t.trace.retrieved})
        titles = db.document_titles(conn, case.tenant, doc_ids)
    turns = []
    for trace in traces:
        user_message = messages.get((trace.turn_no, "user"))
        reply = messages.get((trace.turn_no, "assistant"))
        if user_message is None or reply is None:
            raise MissingTurnMessage(f"case {case_id} turn {trace.turn_no} lacks a message")
        turns.append(CaseTurn(trace, user_message, reply))
    return CaseTurns(turns=turns, total=total, document_titles=titles)


def delete_case(pool: ConnectionPool, case_id: UUID) -> tuple[str, int] | None:
    """Delete a case and everything it owns; its tenant and turn count, or None if there is
    no such case. A turn still running on it then fails its version check (`CaseChanged`)
    and stores nothing."""
    with pool.connection() as conn, conn.transaction():
        return db.delete_case(conn, case_id)


@dataclass(frozen=True)
class SummaryInput:
    """What the summary is made from: the case (facts, annotations, actions) at one
    version, its turn count and its latest messages, oldest first."""

    snapshot: CaseSnapshot
    turns: int
    messages: list[Event]
    omitted: int


def read_summary_input(
    pool: ConnectionPool, case_id: UUID, *, message_limit: int
) -> SummaryInput | None:
    """The case as one snapshot, with its latest `message_limit` messages; None if there is
    no such case."""
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        case = db.get_case(conn, case_id)
        if case is None:
            return None
        turns = db.count_turns(conn, case_id)
        events = db.list_annotations(conn, case_id)
        actions = db.list_actions(conn, case_id)
        messages = db.list_messages(conn, case_id, last=message_limit)
    # Each turn stores two messages (`commit_turn`).
    omitted = max(0, 2 * turns - len(messages))
    return SummaryInput(
        snapshot=CaseSnapshot(case=case, events=events, actions=actions),
        turns=turns,
        messages=messages,
        omitted=omitted,
    )


def store_summary(
    pool: ConnectionPool, case_id: UUID, summary: SummaryRecord
) -> tuple[StoredSummary, int, bool] | None:
    """Store the case's summary (unless one from a newer case version is there) and read
    back what is stored, the case's current version and whether this one was stored; None
    if the case is gone (deleted meanwhile). Never changes the case itself."""
    with pool.connection() as conn, conn.transaction():
        # A key-share lock: a concurrent delete waits, turns (plain updates) do not.
        row = conn.execute(
            "select version from problems where id = %s for key share", (case_id,)
        ).fetchone()
        if row is None:
            return None
        stored = db.upsert_case_summary(conn, case_id, summary)
        current = db.get_case_summary(conn, case_id)
    assert current is not None
    return current, row[0], stored
