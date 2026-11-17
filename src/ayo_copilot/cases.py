"""Admin operations on the copilot's cases (every channel). These functions own the
transactions; the SQL lives in `db/conversations.py`."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from psycopg_pool import ConnectionPool

from ayo_copilot.conversation.case import Case, Event, Phase
from ayo_copilot.conversation.store import SessionAction
from ayo_copilot.db import conversations as db
from ayo_copilot.db.conversations import CaseRow


@dataclass(frozen=True)
class CaseDetail:
    """One case for the admin view: its listing row, the facts and version, the
    annotations and the actions (with `overdue`). Messages and traces are paged apart."""

    row: CaseRow
    case: Case
    events: list[Event]
    actions: list[SessionAction]


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
    """A case with its facts, annotations and actions; None if there is no such case.

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
    return CaseDetail(
        row=row,
        case=case,
        events=events,
        actions=[SessionAction(action, action.is_overdue(today)) for action in actions],
    )
