"""GET /admin/health through HTTP on a real database, with stand-ins for failing services."""

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.app import create_app
from ayo_copilot.config import database_host
from ayo_copilot.dependencies import get_embedder, get_embedding_monitor, get_pool
from ayo_copilot.health import EmbeddingMonitor, TrackedEmbedder, classify_database_location
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from tests.api.test_documents_read import doc, make_client, make_settings

pytestmark = pytest.mark.integration

HTTP_503 = "Embedding provider returned HTTP 503"


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str) -> Iterator[TestClient]:
    with make_client(create_app(make_settings(migrated_database_url))) as client:
        yield client


def service_health(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/admin/health", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def upload(client: TestClient, source_key: str = "a.md"):
    return client.post(
        "/admin/documents",
        files={"file": (source_key, doc("A").encode(), "text/markdown")},
        data={"tenant": "acme"},
    )


class FailingEmbedder:
    def probe(self, *, timeout_seconds: float) -> None:
        raise EmbeddingError(HTTP_503)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError(HTTP_503)


class TimingOutPool:
    @contextmanager
    def connection(self, timeout: float):
        raise PoolTimeout("no connection")
        yield


def test_with_the_fake_provider_everything_is_up(client: TestClient) -> None:
    body = service_health(client)

    assert body["status"] == "ok"
    assert body["database"]["status"] == "up" and body["database"]["error"] is None
    embeddings = body["embeddings"]
    assert {k: embeddings[k] for k in ("status", "provider", "error", "cached")} == {
        "status": "up",
        "provider": "fake",
        "error": None,
        "cached": False,
    }
    assert datetime.fromisoformat(embeddings["checked_at"]).utcoffset().total_seconds() == 0
    assert (embeddings["last_success_at"], embeddings["last_error_at"]) == (None, None)


def test_the_check_is_cached_unless_refreshed(client: TestClient) -> None:
    first = service_health(client)["embeddings"]

    again = service_health(client)["embeddings"]
    refreshed = service_health(client, refresh="true")["embeddings"]

    assert (again["cached"], again["checked_at"]) == (True, first["checked_at"])
    assert refreshed["cached"] is False


def test_a_failing_provider_is_degraded_with_its_error(client: TestClient) -> None:
    failing = FailingEmbedder()
    monitor = EmbeddingMonitor(failing, TrackedEmbedder(failing))
    client.app.dependency_overrides[get_embedding_monitor] = lambda: monitor

    body = service_health(client)

    assert body["status"] == "degraded"
    assert body["database"]["status"] == "up"
    assert (body["embeddings"]["status"], body["embeddings"]["error"]) == ("down", HTTP_503)
    # Liveness is not affected.
    assert client.get("/health").json() == {"status": "ok"}


def test_a_database_without_connections_is_down(client: TestClient) -> None:
    client.app.dependency_overrides[get_pool] = TimingOutPool

    body = service_health(client)

    assert body["status"] == "degraded"
    assert (body["database"]["status"], body["database"]["error"]) == ("down", "timeout")
    assert body["embeddings"]["status"] == "up"


def test_real_embedding_calls_are_tracked(client: TestClient) -> None:
    # The app's own embedder: the lifespan wraps it in the tracker the report reads.
    assert upload(client).status_code == 201

    embeddings = service_health(client)["embeddings"]

    assert embeddings["last_success_at"] is not None
    assert (embeddings["last_error_at"], embeddings["last_error"]) == (None, None)


def test_a_failed_upload_shows_as_the_last_error(client: TestClient) -> None:
    tracker = TrackedEmbedder(FailingEmbedder())
    client.app.dependency_overrides[get_embedder] = lambda: tracker
    client.app.dependency_overrides[get_embedding_monitor] = lambda: EmbeddingMonitor(
        FakeEmbedder(dimensions=1024), tracker
    )

    assert upload(client).status_code == 502
    embeddings = service_health(client)["embeddings"]

    assert embeddings["status"] == "up"  # the check itself passes
    assert embeddings["last_error"] == HTTP_503
    assert embeddings["last_error_at"] is not None and embeddings["last_success_at"] is None


def test_refresh_must_be_a_boolean(client: TestClient) -> None:
    response = client.get("/admin/health", params={"refresh": "maybe"})

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == ("bool_parsing", ["query", "refresh"])


def test_the_database_reports_where_it_runs_and_its_versions(
    client: TestClient, migrated_database_url: str
) -> None:
    database = service_health(client)["database"]

    # testcontainers may report a Docker host other than localhost: ask the classifier.
    assert database["location"] == classify_database_location(migrated_database_url)
    assert re.fullmatch(r"\d+(\.\d+)*", database["postgres_version"])
    assert re.fullmatch(r"\d+(\.\d+)*", database["pgvector_version"])


def test_the_body_never_names_the_database_host(
    client: TestClient, migrated_database_url: str
) -> None:
    host = database_host(migrated_database_url)
    body = client.get("/admin/health").text

    assert host and host not in body
    assert "postgresql://" not in body


def test_a_database_that_is_down_keeps_its_location(
    client: TestClient, migrated_database_url: str
) -> None:
    client.app.dependency_overrides[get_pool] = TimingOutPool

    database = service_health(client)["database"]

    assert database["location"] == classify_database_location(migrated_database_url)
    assert (database["postgres_version"], database["pgvector_version"]) == (None, None)
