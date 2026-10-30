"""Admin operations on stored documents. These functions own the transactions; the SQL
lives in `db/repository.py`."""

from psycopg_pool import ConnectionPool

from ayo_copilot.db import repository
from ayo_copilot.db.repository import DocumentRow


def read_document_page(
    pool: ConnectionPool,
    *,
    tenant: str | None = None,
    q: str | None = None,
    sort: str = repository.DEFAULT_SORT,
    limit: int,
    offset: int,
) -> tuple[list[DocumentRow], int]:
    """One page of documents and the total matching the filters.

    Repeatable read: the page and the count are two statements, and under read committed
    an upload between them could make `total` disagree with the items.
    """
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        return repository.list_documents(
            conn, tenant=tenant, q=q, sort=sort, limit=limit, offset=offset
        )


def read_document(pool: ConnectionPool, doc_id: str) -> DocumentRow | None:
    with pool.connection() as conn:
        return repository.get_document(conn, doc_id)


def read_markdown(pool: ConnectionPool, doc_id: str) -> str | None:
    with pool.connection() as conn:
        return repository.get_markdown(conn, doc_id)
