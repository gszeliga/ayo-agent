"""Admin operations on the copilot's cases (every channel). These functions own the
transactions; the SQL lives in `db/conversations.py`."""

from datetime import date

from psycopg_pool import ConnectionPool

from ayo_copilot.conversation.case import Phase
from ayo_copilot.db import conversations as db
from ayo_copilot.db.conversations import CaseRow


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
