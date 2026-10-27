import logging
import uuid
from urllib.parse import urlsplit

import psycopg
import pytest
from pgvector import Vector
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.db.pool import open_pool

pytestmark = pytest.mark.integration


def _insert_document(pool: ConnectionPool, doc_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            insert into documents (doc_id, tenant, source_key, markdown_path,
                                   content_hash, chunk_signature, embed_signature)
            values (%s, 'acme', 'a.md', 'p', 'h', 'c', 'e')
            """,
            (doc_id,),
        )


def test_vector_parameters_round_trip(db_pool: ConnectionPool) -> None:
    with db_pool.connection() as conn:
        (value,) = conn.execute("select %s::vector", (Vector([1.0, 2.5, -3.0]),)).fetchone()

    assert value == Vector([1.0, 2.5, -3.0])


def test_vectors_are_read_back_from_chunks(db_pool: ConnectionPool) -> None:
    embedding = Vector([0.5] * 1024)
    _insert_document(db_pool, "upload-000000000001")
    with db_pool.connection() as conn:
        conn.execute(
            "insert into chunks (document_id, chunk_index, chunk_text, embedding)"
            " select id, 0, 'texto', %s from documents",
            (embedding,),
        )
        (value,) = conn.execute("select embedding from chunks").fetchone()

    assert value == embedding


def test_every_pooled_connection_is_configured(migrated_database_url: str) -> None:
    pool = open_pool(migrated_database_url, min_size=2, max_size=2)
    try:
        with pool.connection() as first, pool.connection() as second:
            assert first is not second
            for conn in (first, second):
                (value,) = conn.execute("select '[1,2]'::vector").fetchone()
                assert value == Vector([1.0, 2.0])
    finally:
        pool.close()


def test_open_pool_fails_fast_without_the_vector_extension(scratch_database_url: str) -> None:
    with pytest.raises(PoolTimeout):
        open_pool(scratch_database_url, timeout=2)


# These two tests insert the same doc_id: both pass only if each starts with empty tables.
@pytest.mark.parametrize("attempt", [1, 2])
def test_tables_are_empty_at_the_start_of_each_test(db_pool: ConnectionPool, attempt: int) -> None:
    _insert_document(db_pool, "upload-00000000000a")

    with db_pool.connection() as conn:
        assert conn.execute("select count(*) from documents").fetchone() == (1,)


def test_debug_logs_show_the_pool_but_never_the_password(
    postgres_server_url: str, migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    role = f"log_{uuid.uuid4().hex[:8]}"
    password = f"pw-{uuid.uuid4().hex}"
    with psycopg.connect(postgres_server_url, autocommit=True) as conn:
        conn.execute(f"create role {role} login password '{password}'")
    parts = urlsplit(migrated_database_url)
    url = parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}").geturl()
    caplog.set_level(logging.DEBUG, logger="psycopg")
    try:
        pool = open_pool(url)
        with pool.connection() as conn:
            conn.execute("select 1")
        pool.close()
    finally:
        with psycopg.connect(postgres_server_url, autocommit=True) as conn:
            conn.execute(f"drop role {role}")

    assert "pool 'ayo' is ready to use" in caplog.text
    assert "connection attempt" in caplog.text
    assert password not in caplog.text
