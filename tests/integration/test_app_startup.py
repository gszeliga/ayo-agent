import logging

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ayo_copilot import app as app_module
from ayo_copilot.app import StartupError, create_app
from ayo_copilot.config import Settings

pytestmark = pytest.mark.integration


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": database_url,
        # testcontainers may report a Docker host other than localhost.
        "allow_remote_database": True,
        "admin_api_key": "test-admin-key",
        "embedding_provider": "fake",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def start(app: FastAPI) -> None:
    """Run the app's startup and shutdown."""
    with TestClient(app):
        pass


@pytest.fixture(autouse=True)
def short_pool_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "POOL_OPEN_TIMEOUT_SECONDS", 2.0)


def test_startup_opens_the_pool_and_shutdown_closes_it(migrated_database_url: str) -> None:
    settings = make_settings(migrated_database_url)

    with TestClient(create_app(settings)) as client:
        pool = client.app_state["pool"]
        assert client.app_state["settings"] is settings
        with pool.connection() as conn:
            assert conn.execute("select 1").fetchone() == (1,)
        assert client.get("/health").status_code == 200

    assert pool.closed


def test_startup_fails_when_dimensions_differ(migrated_database_url: str) -> None:
    app = create_app(make_settings(migrated_database_url, embedding_dimensions=512))

    with pytest.raises(StartupError, match=r"vector\(1024\).*EMBEDDING_DIMENSIONS=512"):
        start(app)


def test_startup_fails_clearly_without_the_vector_extension(
    scratch_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="psycopg")
    app = create_app(make_settings(scratch_database_url))

    with pytest.raises(StartupError, match="alembic upgrade head"):
        start(app)
    assert "vector type not found" in caplog.text


def test_startup_fails_clearly_without_the_chunks_table(scratch_database_url: str) -> None:
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("create extension vector")
    app = create_app(make_settings(scratch_database_url))

    with pytest.raises(StartupError, match="table chunks not found"):
        start(app)


def test_startup_applies_the_db_log_level(migrated_database_url: str) -> None:
    psycopg_logger = logging.getLogger("psycopg")
    previous = psycopg_logger.level
    try:
        with TestClient(create_app(make_settings(migrated_database_url, db_log_level="INFO"))):
            assert psycopg_logger.level == logging.INFO
    finally:
        psycopg_logger.setLevel(previous)


def test_startup_warns_about_the_fake_embedder(
    migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="ayo_copilot")

    start(create_app(make_settings(migrated_database_url)))

    [record] = [r for r in caplog.records if r.getMessage().startswith("embedder:")]
    assert record.levelno == logging.WARNING
    assert record.getMessage().startswith("embedder: fake")
    assert "dimensions=1024" in record.getMessage()


def test_startup_logs_the_voyage_embedder_without_the_key(
    migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    settings = make_settings(
        migrated_database_url,
        embedding_provider="voyage",
        voyage_api_key="pa-test-secret-key",
        embedding_batch_size=64,
    )

    # Building the client makes no request, so this never reaches Voyage.
    start(create_app(settings))

    [record] = [r for r in caplog.records if r.getMessage().startswith("embedder:")]
    assert record.levelno == logging.INFO
    assert record.getMessage() == (
        "embedder: voyage model=voyage-4 dimensions=1024 batch_size=64"
        " base_url=https://api.voyageai.com/v1"
    )
    assert "pa-test-secret-key" not in caplog.text
