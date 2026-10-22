import os
import uuid
from collections.abc import Iterator

import docker
import psycopg
import pytest
from docker.errors import DockerException

from tests.integration.support import PGVECTOR_IMAGE, is_neon_url, with_database


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
