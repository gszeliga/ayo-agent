import logging

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg_pool import ConnectionPool

POOL_NAME = "ayo"


def set_db_log_level(level: str) -> None:
    """Set the level of psycopg's own logs; `psycopg.pool` inherits it.

    psycopg logs hosts and ports, never passwords. It defaults to WARNING.
    """
    logging.getLogger("psycopg").setLevel(level)


def _configure(conn: Connection) -> None:
    register_vector(conn)
    # register_vector queries the catalog, which opens a transaction; the pool discards
    # connections that configure leaves outside the IDLE state.
    conn.commit()


def open_pool(
    database_url: str, *, min_size: int = 1, max_size: int = 5, timeout: float = 10.0
) -> ConnectionPool:
    """Open a pool whose connections load and dump pgvector values.

    Waits until `min_size` connections are ready, so a wrong URL or a database without
    the `vector` extension fails here instead of on the first request.
    """
    pool = ConnectionPool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        name=POOL_NAME,
        configure=_configure,
        open=False,
    )
    try:
        pool.open(wait=True, timeout=timeout)
    except BaseException:
        pool.close()
        raise
    return pool
