"""The database schema revision this code expects, and what the database has.

The revisions are listed here, not read from `migrations/` at runtime: that folder is not
part of the package. `tests/unit/test_db_schema.py` fails when this list and the Alembic
chain differ, so a new migration must be added here too.
"""

import logging

from psycopg import Connection

# Every Alembic revision, oldest first; the last one is the head this code expects.
SCHEMA_REVISIONS: tuple[str, ...] = ("0001", "0002", "0003", "0004")

UPGRADE_HINT = "run `uv run alembic upgrade head`"


def read_schema_revision(conn: Connection) -> str | None:
    """The revision Alembic recorded, or None when it recorded none (no table, or empty).

    A branched history would store several rows; they are joined with "+".
    """
    exists = conn.execute("select to_regclass('alembic_version') is not null").fetchone()
    if not exists or not exists[0]:
        return None
    rows = conn.execute("select version_num from alembic_version order by version_num").fetchall()
    if not rows:
        return None
    return "+".join(row[0] for row in rows)


def describe_schema(revision: str | None) -> tuple[int, str]:
    """The log level and line for the database's revision against `SCHEMA_REVISIONS`."""
    head = SCHEMA_REVISIONS[-1]
    if revision is None:
        return logging.WARNING, f"database schema: no Alembic revision recorded: {UPGRADE_HINT}"
    if revision == head:
        return logging.INFO, f"database schema: revision {revision} (current)"
    if revision in SCHEMA_REVISIONS:
        return (
            logging.WARNING,
            f"database schema: revision {revision}, outdated (code expects {head}): {UPGRADE_HINT}",
        )
    return (
        logging.WARNING,
        f"database schema: revision {revision} unknown to this code (expects {head}): the"
        " database is newer than the code, or was migrated from another branch",
    )
