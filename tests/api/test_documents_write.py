"""PATCH /admin/documents/{doc_id} and POST .../reprocess, through HTTP on a real database."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.dependencies import get_embedder
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from tests.api.test_documents_read import doc, listing, make_client, make_settings, upload

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pro-014-control-sellado.md"


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str) -> Iterator[TestClient]:
    with make_client(create_app(make_settings(migrated_database_url))) as client:
        yield client


def rename(client: TestClient, doc_id: str, body: Any):
    return client.patch(f"/admin/documents/{doc_id}", json=body)


def test_rename_returns_the_renamed_document(client: TestClient) -> None:
    doc_id = upload(client, "valvula.md", doc("Válvula de purga"))
    before = client.get(f"/admin/documents/{doc_id}").json()

    response = rename(client, doc_id, {"title": "  Válvula de purga (rev. 2)  "})

    assert response.status_code == 200, response.text
    renamed = response.json()
    assert renamed == client.get(f"/admin/documents/{doc_id}").json()
    assert renamed["title"] == "Válvula de purga (rev. 2)"
    assert datetime.fromisoformat(renamed["updated_at"]) > datetime.fromisoformat(
        before["updated_at"]
    )
    unchanged = {k: v for k, v in before.items() if k not in ("title", "updated_at")}
    assert {k: renamed[k] for k in unchanged} == unchanged


def test_rename_never_touches_chunks_or_the_embedder(client: TestClient) -> None:
    embedder = FakeEmbedder(dimensions=1024)
    client.app.dependency_overrides[get_embedder] = lambda: embedder
    doc_id = upload(client, "pro-014.md", FIXTURE.read_text())
    chunks_url = f"/admin/documents/{doc_id}/chunks?include_embedding=true"
    chunks_before = client.get(chunks_url).json()
    calls_after_upload = len(embedder.calls)

    assert rename(client, doc_id, {"title": "Sellado"}).status_code == 200

    assert len(embedder.calls) == calls_after_upload
    assert client.get(chunks_url).json() == chunks_before


def test_renamed_document_shows_in_the_listing_first(client: TestClient) -> None:
    first = upload(client, "a.md", doc("A"))
    upload(client, "b.md", doc("B"))

    rename(client, first, {"title": "A renombrado"})

    top = listing(client)["items"][0]
    assert (top["doc_id"], top["title"]) == (first, "A renombrado")


def test_rename_to_the_same_title_is_a_no_op(client: TestClient) -> None:
    doc_id = upload(client, "a.md", doc("Sellado"))
    before = client.get(f"/admin/documents/{doc_id}").json()

    response = rename(client, doc_id, {"title": " Sellado "})

    assert response.status_code == 200
    assert response.json() == before


def test_rename_of_an_unknown_document_is_a_404(client: TestClient) -> None:
    response = rename(client, "upload-000000000000", {"title": "Nuevo"})

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "document_not_found"


@pytest.mark.parametrize(
    ("doc_id", "body", "loc", "type"),
    [
        ("pro-014.md", {"title": "Nuevo"}, ["path", "doc_id"], "string_pattern_mismatch"),
        ("upload-000000000000", {"title": "   "}, ["body", "title"], "string_too_short"),
        ("upload-000000000000", {"title": "a" * 201}, ["body", "title"], "string_too_long"),
        ("upload-000000000000", {"title": None}, ["body", "title"], "string_type"),
        ("upload-000000000000", {}, ["body", "title"], "missing"),
        (
            "upload-000000000000",
            {"title": "Nuevo", "source_key": "otro.md"},
            ["body", "source_key"],
            "extra_forbidden",
        ),
    ],
)
def test_invalid_renames_are_a_422(
    client: TestClient, doc_id: str, body: dict[str, Any], loc: list[str], type: str
) -> None:
    response = rename(client, doc_id, body)

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == (type, loc)


def test_a_body_that_is_not_json_is_a_422(client: TestClient) -> None:
    response = client.patch(
        "/admin/documents/upload-000000000000",
        content=b"{title: Nuevo}",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "json_invalid"


class FailingEmbedder:
    def embed_documents(self, texts: Any) -> list[list[float]]:
        raise EmbeddingError("provider returned HTTP 503")


def reprocess(client: TestClient, doc_id: str, **params: Any):
    return client.post(f"/admin/documents/{doc_id}/reprocess", params=params)


def test_reprocess_brings_an_outdated_document_back_to_indexed(
    client: TestClient, migrated_database_url: str
) -> None:
    doc_id = upload(client, "pro-014.md", FIXTURE.read_text())
    rename(client, doc_id, {"title": "Sellado (rev. 2)"})
    before = client.get(f"/admin/documents/{doc_id}").json()

    changed = create_app(make_settings(migrated_database_url, chunk_size=300))
    with make_client(changed) as other:
        assert other.get(f"/admin/documents/{doc_id}").json()["status"] == "outdated"
        response = reprocess(other, doc_id)
        after = other.get(f"/admin/documents/{doc_id}").json()

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["doc_id"], body["status"]) == (doc_id, "indexed")
    assert body["chunk_count"] == after["chunk_count"] > before["chunk_count"]
    assert body["embed_signature"] == after["embed_signature"]
    assert (after["status"], after["outdated_reason"]) == ("indexed", None)
    kept = ("title", "content_hash", "size_bytes", "created_at", "updated_at")
    assert {k: after[k] for k in kept} == {k: before[k] for k in kept}


def test_reprocess_of_an_up_to_date_document_does_nothing(client: TestClient) -> None:
    embedder = FakeEmbedder(dimensions=1024)
    client.app.dependency_overrides[get_embedder] = lambda: embedder
    doc_id = upload(client, "a.md", doc("A"))
    before = client.get(f"/admin/documents/{doc_id}").json()
    calls = len(embedder.calls)

    response = reprocess(client, doc_id)

    assert response.status_code == 200
    assert response.json() == {"doc_id": doc_id, "status": "up_to_date"}
    assert len(embedder.calls) == calls
    assert client.get(f"/admin/documents/{doc_id}").json() == before


def test_force_reprocesses_anyway(client: TestClient) -> None:
    doc_id = upload(client, "a.md", doc("A"))
    before = client.get(f"/admin/documents/{doc_id}").json()

    response = reprocess(client, doc_id, force="true")

    assert response.status_code == 200
    assert response.json()["status"] == "indexed"
    after = client.get(f"/admin/documents/{doc_id}").json()
    assert datetime.fromisoformat(after["embedded_at"]) > datetime.fromisoformat(
        before["embedded_at"]
    )
    assert after["updated_at"] == before["updated_at"]


def test_reprocess_provider_failure_is_a_502_and_changes_nothing(client: TestClient) -> None:
    doc_id = upload(client, "pro-014.md", FIXTURE.read_text())
    url = f"/admin/documents/{doc_id}"
    before = (client.get(url).json(), client.get(f"{url}/chunks?include_embedding=true").json())
    client.app.dependency_overrides[get_embedder] = FailingEmbedder

    response = reprocess(client, doc_id, force="true")

    assert response.status_code == 502
    assert response.json()["detail"][0]["type"] == "embedding_failed"
    after = (client.get(url).json(), client.get(f"{url}/chunks?include_embedding=true").json())
    assert after == before


def test_reprocess_of_an_unknown_document_is_a_404(client: TestClient) -> None:
    response = reprocess(client, "upload-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "document_not_found"


@pytest.mark.parametrize(
    ("doc_id", "params", "loc", "type"),
    [
        ("pro-014.md", {}, ["path", "doc_id"], "string_pattern_mismatch"),
        ("upload-000000000000", {"force": "maybe"}, ["query", "force"], "bool_parsing"),
    ],
)
def test_invalid_reprocess_requests_are_a_422(
    client: TestClient, doc_id: str, params: dict[str, str], loc: list[str], type: str
) -> None:
    response = reprocess(client, doc_id, **params)

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == (type, loc)
