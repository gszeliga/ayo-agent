"""Case summaries against real Postgres: reading, the upsert and its version guard, and
that a summary never touches the case itself."""

from dataclasses import replace
from uuid import UUID

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.db import conversations as db
from ayo_copilot.db.conversations import SummaryRecord

pytestmark = pytest.mark.integration

SUMMARY = SummaryRecord(
    content="La línea 2 pierde un 4 % en el envasado desde el lunes.",
    source_version=3,
    model="openai/gpt-4.1-mini",
    prompts_version="summary-1",
    total_tokens=812,
    cost=0.000412,
)


def new_case(pool: ConnectionPool, version: int = 3) -> UUID:
    with pool.connection() as conn:
        row = conn.execute(
            "insert into problems (tenant, version, updated_at)"
            " values ('cliente-acme', %s, '2026-11-10 10:00+00') returning id",
            (version,),
        ).fetchone()
    assert row is not None
    return row[0]


def upsert(pool: ConnectionPool, problem_id: UUID, summary: SummaryRecord) -> bool:
    with pool.connection() as conn:
        return db.upsert_case_summary(conn, problem_id, summary)


def get(pool: ConnectionPool, problem_id: UUID) -> db.StoredSummary | None:
    with pool.connection() as conn:
        return db.get_case_summary(conn, problem_id)


def test_no_summary_until_one_is_stored(db_pool: ConnectionPool) -> None:
    assert get(db_pool, new_case(db_pool)) is None


def test_stored_summary_reads_back(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)

    assert upsert(db_pool, problem_id, SUMMARY)
    stored = get(db_pool, problem_id)

    assert stored is not None
    assert stored.summary == SUMMARY
    assert stored.created_at is not None


def test_unknown_values_read_back_as_none(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    upsert(db_pool, problem_id, replace(SUMMARY, total_tokens=None, cost=None))

    stored = get(db_pool, problem_id)

    assert stored is not None
    assert (stored.summary.total_tokens, stored.summary.cost) == (None, None)


def test_a_summary_from_the_same_or_a_newer_version_replaces_it(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool, version=5)
    upsert(db_pool, problem_id, SUMMARY)
    first = get(db_pool, problem_id)

    assert upsert(db_pool, problem_id, replace(SUMMARY, content="Otra vez"))
    assert upsert(db_pool, problem_id, replace(SUMMARY, content="Nueva", source_version=5))

    stored = get(db_pool, problem_id)
    assert stored is not None and first is not None
    assert (stored.summary.content, stored.summary.source_version) == ("Nueva", 5)
    assert stored.created_at >= first.created_at


def test_a_summary_from_an_older_version_is_ignored(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool, version=5)
    upsert(db_pool, problem_id, replace(SUMMARY, source_version=5))

    assert not upsert(db_pool, problem_id, replace(SUMMARY, content="Vieja", source_version=4))

    stored = get(db_pool, problem_id)
    assert stored is not None
    assert (stored.summary.content, stored.summary.source_version) == (SUMMARY.content, 5)


def test_storing_a_summary_leaves_the_case_alone(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool, version=3)

    upsert(db_pool, problem_id, SUMMARY)
    upsert(db_pool, problem_id, replace(SUMMARY, content="Otra"))

    with db_pool.connection() as conn:
        row = conn.execute(
            "select version, updated_at = '2026-11-10 10:00+00' from problems where id = %s",
            (problem_id,),
        ).fetchone()
    assert row == (3, True)


def test_deleting_the_case_deletes_its_summary(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    upsert(db_pool, problem_id, SUMMARY)

    with db_pool.connection() as conn:
        assert db.delete_case(conn, problem_id) is not None

    assert get(db_pool, problem_id) is None


def test_summary_content_is_not_in_repr(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    upsert(db_pool, problem_id, SUMMARY)

    stored = get(db_pool, problem_id)

    assert "línea" not in repr(SUMMARY)
    assert "línea" not in repr(stored)
