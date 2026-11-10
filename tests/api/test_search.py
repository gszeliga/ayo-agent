"""POST /admin/search through HTTP, against a real pgvector and the fake embedder."""

import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.dependencies import get_embedder
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.service import current_configs

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pro-014-control-sellado.md"
API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
SETTINGS = Settings(_env_file=None, admin_api_key=API_KEY, embedding_provider="fake")
CHUNKER, EMBEDDER = current_configs(SETTINGS)
# Marks text that must never reach a log line or an error body.
SECRET_QUERY = "¿Cuál es la presión confidencial de la línea 3?"


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("not called by a search")

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("Embedding provider returned HTTP 503")


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimensions=1024)


@pytest.fixture
def app(db_pool: ConnectionPool, migrated_database_url: str, embedder: FakeEmbedder) -> FastAPI:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        # testcontainers may report a Docker host other than localhost.
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
    )
    app = create_app(settings, docs_enabled=True)
    app.dependency_overrides[get_embedder] = lambda: embedder
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def upload(client: TestClient, tenant: str = "acme", filename: str = "pro-014.md") -> str:
    response = client.post(
        "/admin/documents",
        files={"file": (filename, FIXTURE.read_bytes(), "text/markdown")},
        data={"tenant": tenant},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["doc_id"]


def search(client: TestClient, **body: object):
    return client.post("/admin/search", json=body, headers=HEADERS)


def embedded_text_with(embedder: FakeEmbedder, needle: str) -> str:
    """The text an uploaded chunk was embedded as: the fake gives a query of exactly that
    text the chunk's own vector."""
    return next(text for batch in embedder.calls for text in batch if needle in text)


def test_a_chunk_is_found_by_its_own_text(client: TestClient, embedder: FakeEmbedder) -> None:
    doc_id = upload(client)
    query = embedded_text_with(embedder, "Presión")

    response = search(client, query=f"  {query}  ", top_k=3)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == query
    assert body["skipped"] == {"embedder_mismatch": 0}
    assert body["debug"] is None
    best = body["results"][0]
    assert (best["rank"], best["similarity"]) == (1, 1.0)
    assert best["doc_id"] == doc_id
    assert best["document_title"] == "PRO-014 Control de sellado"
    assert (best["source_key"], best["tenant"]) == ("pro-014.md", "acme")
    assert best["heading"] == "PRO-014 Control de sellado > 3. Pasos > 3.2 Medición"
    assert "Presión" in best["chunk_text"]
    assert best["char_count"] == len(best["chunk_text"])
    assert best["embedder_outdated"] is False
    assert [r["rank"] for r in body["results"]] == [1, 2, 3]
    assert embedder.query_calls == [query]
    # `chunk_index` points at the same chunk in the document's chunks listing.
    chunks = client.get(f"/admin/documents/{doc_id}/chunks", headers=HEADERS).json()["items"]
    assert chunks[best["chunk_index"]]["chunk_text"] == best["chunk_text"]


def test_tenant_filter_through_http(client: TestClient, embedder: FakeEmbedder) -> None:
    upload(client, tenant="cliente-acme")
    upload(client, tenant="cliente-globex")
    upload(client, tenant="ayo")
    query = embedded_text_with(embedder, "Presión")

    body = search(client, query=query, tenants=["cliente-acme", "ayo"], top_k=50).json()

    assert {r["tenant"] for r in body["results"]} == {"cliente-acme", "ayo"}
    every = search(client, query=query, top_k=50).json()
    assert {r["tenant"] for r in every["results"]} == {"cliente-acme", "cliente-globex", "ayo"}


def test_outdated_documents_are_skipped_or_flagged(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    upload(client, filename="actual.md")
    old = upload(client, filename="viejo.md")
    with db_pool.connection() as conn:
        conn.execute(
            "update documents set embedder_config = 'voyage-3/document/1024' where doc_id = %s",
            (old,),
        )

    default = search(client, query="presión de sellado", top_k=50).json()
    included = search(client, query="presión de sellado", top_k=50, include_outdated=True).json()

    assert default["skipped"] == {"embedder_mismatch": 1}
    assert old not in {r["doc_id"] for r in default["results"]}
    assert included["skipped"] == {"embedder_mismatch": 0}
    flags = {(r["doc_id"], r["embedder_outdated"]) for r in included["results"]}
    assert (old, True) in flags
    assert all(flag for doc_id, flag in flags if doc_id == old)
    assert not any(flag for doc_id, flag in flags if doc_id != old)


def test_debug_reports_configs_and_timings(client: TestClient) -> None:
    upload(client)

    body = search(client, query="  presión  ", debug=True).json()

    debug = body["debug"]
    assert debug["embedded_query"] == "presión"
    assert debug["input_type"] == "query"
    assert (debug["embedder_config"], debug["chunker_config"]) == (EMBEDDER, CHUNKER)
    timings = debug["timings_ms"]
    assert set(timings) == {"embed", "search", "total"}
    assert all(value >= 0 for value in timings.values())
    assert timings["total"] >= timings["search"]


def test_min_similarity_and_doc_ids(client: TestClient, embedder: FakeEmbedder) -> None:
    doc_id = upload(client, filename="uno.md")
    upload(client, filename="dos.md")
    query = embedded_text_with(embedder, "Presión")

    only_one = search(client, query=query, doc_ids=[doc_id], top_k=50).json()
    exact = search(client, query=query, min_similarity=0.9999, top_k=50).json()

    assert {r["doc_id"] for r in only_one["results"]} == {doc_id}
    # The same chunk in both documents: identical vectors, ties by chunk id.
    assert [r["similarity"] for r in exact["results"]] == [1.0, 1.0]


def test_empty_knowledge_base(client: TestClient) -> None:
    response = search(client, query="¿Qué es OEE?")

    assert response.status_code == 200
    assert response.json() == {
        "query": "¿Qué es OEE?",
        "results": [],
        "skipped": {"embedder_mismatch": 0},
        "debug": None,
    }


def test_unknown_tenant_or_document_is_not_an_error(client: TestClient) -> None:
    upload(client)

    assert search(client, query="q", tenants=["cliente-nadie"]).json()["results"] == []
    assert search(client, query="q", doc_ids=["upload-000000000000"]).json()["results"] == []


def test_embedder_failure_is_a_502_without_details(
    app: FastAPI, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    app.dependency_overrides[get_embedder] = FailingEmbedder

    with caplog.at_level(logging.DEBUG):
        response = search(client, query=SECRET_QUERY)

    assert response.status_code == 502
    assert response.json() == {
        "detail": [{"type": "embedding_failed", "loc": [], "msg": "embedding provider failed"}]
    }
    assert SECRET_QUERY not in caplog.text


@pytest.mark.parametrize(
    ("body", "error_type", "loc"),
    [
        ({"query": "   "}, "string_too_short", ["body", "query"]),
        ({"query": "q", "top_k": 51}, "less_than_equal", ["body", "top_k"]),
        (
            {"query": "q", "tenants": ["Cliente ACME"]},
            "string_pattern_mismatch",
            ["body", "tenants", 0],
        ),
        ({"query": "q", "doc_ids": []}, "too_short", ["body", "doc_ids"]),
        ({"query": "q", "debug": "maybe"}, "bool_parsing", ["body", "debug"]),
    ],
)
def test_invalid_bodies_are_422(
    client: TestClient, body: dict[str, object], error_type: str, loc: list[object]
) -> None:
    response = search(client, **body)

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert (error["type"], error["loc"]) == (error_type, loc)


def test_logs_carry_neither_the_query_nor_the_chunks(
    client: TestClient, embedder: FakeEmbedder, caplog: pytest.LogCaptureFixture
) -> None:
    upload(client)
    query = embedded_text_with(embedder, "Presión")
    caplog.clear()

    with caplog.at_level(logging.DEBUG):
        results = search(client, query=SECRET_QUERY, tenants=["acme"]).json()["results"]
        search(client, query=query)

    assert results
    assert "tenants=acme" in caplog.text
    assert SECRET_QUERY not in caplog.text
    assert "Presión" not in caplog.text
