import os
import uuid
from collections.abc import Iterator

import docker
import psycopg
import pytest
from alembic import command
from docker.errors import DockerException
from psycopg_pool import ConnectionPool

from ayo_copilot.db.pool import open_pool
from tests.integration.support import PGVECTOR_IMAGE, alembic_config, is_neon_url, with_database


@pytest.fixture(scope="session")
def postgres_server_url() -> Iterator[str]:
    """A Postgres server with pgvector: TEST_DATABASE_URL if set, else a testcontainer."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        if is_neon_url(url):
            pytest.fail("TEST_DATABASE_URL points at Neon (production); refusing.", pytrace=False)
        yield url
        return

    try:
        docker.from_env().ping()
    except DockerException:
        pytest.skip("Docker is not available: integration tests skipped")

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(PGVECTOR_IMAGE, driver=None) as container:
        yield container.get_connection_url()


@pytest.fixture
def scratch_database_url(postgres_server_url: str) -> Iterator[str]:
    """A new, empty database on the test server, dropped after the test."""
    name = f"scratch_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(postgres_server_url, autocommit=True) as conn:
        conn.execute(f"create database {name}")
    try:
        yield with_database(postgres_server_url, name)
    finally:
        with psycopg.connect(postgres_server_url, autocommit=True) as conn:
            conn.execute(f"drop database {name} with (force)")


@pytest.fixture(scope="session")
def migrated_database_url(postgres_server_url: str) -> Iterator[str]:
    """A database migrated to head once per session, shared by the repository tests."""
    name = f"ayo_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(postgres_server_url, autocommit=True) as conn:
        conn.execute(f"create database {name}")
    url = with_database(postgres_server_url, name)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        with psycopg.connect(postgres_server_url, autocommit=True) as conn:
            conn.execute(f"drop database {name} with (force)")


@pytest.fixture(scope="session")
def _session_pool(migrated_database_url: str) -> Iterator[ConnectionPool]:
    pool = open_pool(migrated_database_url)
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture
def db_pool(_session_pool: ConnectionPool) -> ConnectionPool:
    """The shared pool, with empty tables: truncated before each test (see ADR 0001)."""
    with _session_pool.connection() as conn:
        conn.execute("truncate documents, chunks restart identity cascade")
    return _session_pool
