"""GET /admin/documents, GET /admin/documents/{doc_id} and its /content, through HTTP on a
real database.

Documents are created with the upload endpoint, so these tests also check that what the
upload stores is what the listing shows.
"""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.ingestion.signatures import make_doc_id

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
DOCUMENT_FIELDS = {
    "doc_id",
    "tenant",
    "title",
    "source_key",
    "status",
    "outdated_reason",
    "chunk_count",
    "size_bytes",
    "content_hash",
    "chunk_signature",
    "embed_signature",
    "chunker_config",
    "embedder_config",
    "created_at",
    "updated_at",
    "chunked_at",
    "embedded_at",
}


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": database_url,
        # testcontainers may report a Docker host other than localhost.
        "allow_remote_database": True,
        "admin_api_key": API_KEY,
        "embedding_provider": "fake",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(app: FastAPI) -> TestClient:
    return TestClient(app, headers=HEADERS)


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str) -> Iterator[TestClient]:
    # `db_pool` empties the tables of the database the app uses.
    with make_client(create_app(make_settings(migrated_database_url))) as client:
        yield client


def upload(client: TestClient, source_key: str, text: str, tenant: str = "acme", **fields: str):
    response = client.post(
        "/admin/documents",
        files={"file": (source_key, text.encode(), "text/markdown")},
        data={"tenant": tenant, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()["doc_id"]


def doc(title: str) -> str:
    return f"# {title}\n\nComprobar la presión de la junta y anotar el valor en el registro.\n"


def listing(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/admin/documents", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def keys(page: dict[str, Any]) -> list[str]:
    return [item["source_key"] for item in page["items"]]


def test_empty_database_gives_an_empty_page(client: TestClient) -> None:
    assert listing(client) == {"items": [], "total": 0, "limit": 25, "offset": 0}


def test_item_shows_what_the_upload_stored(client: TestClient) -> None:
    text = doc("Válvula de purga")
    doc_id = upload(client, "valvula.md", text)

    (item,) = listing(client)["items"]

    assert set(item) == DOCUMENT_FIELDS
    assert item["doc_id"] == doc_id == make_doc_id("acme", "valvula.md")
    assert (item["tenant"], item["title"], item["source_key"]) == (
        "acme",
        "Válvula de purga",
        "valvula.md",
    )
    assert (item["status"], item["outdated_reason"]) == ("indexed", None)
    assert item["chunk_count"] == 1
    assert item["size_bytes"] == len(text.encode()) > len(text)
    settings = make_settings("postgresql://unused")
    assert (item["chunker_config"], item["embedder_config"]) == current_configs(settings)
    assert len(item["content_hash"]) == len(item["chunk_signature"]) == 64
    assert len(item["embed_signature"]) == 64


def test_timestamps_are_utc(client: TestClient) -> None:
    upload(client, "a.md", doc("A"))

    (item,) = listing(client)["items"]

    for field in ("created_at", "updated_at", "chunked_at", "embedded_at"):
        assert item[field].endswith("Z"), item[field]
        assert datetime.fromisoformat(item[field]).tzinfo == UTC


def test_detail_equals_the_listed_item(client: TestClient) -> None:
    doc_id = upload(client, "a.md", doc("A"))
    (item,) = listing(client)["items"]

    response = client.get(f"/admin/documents/{doc_id}")

    assert response.status_code == 200
    assert response.json() == item


def test_changed_settings_make_documents_outdated(
    client: TestClient, migrated_database_url: str
) -> None:
    doc_id = upload(client, "a.md", doc("A"))

    changed = create_app(make_settings(migrated_database_url, chunk_size=300))
    with make_client(changed) as other:
        (item,) = listing(other)["items"]
        detail = other.get(f"/admin/documents/{doc_id}").json()

    assert (item["status"], item["outdated_reason"]) == ("outdated", "chunker_changed")
    assert (detail["status"], detail["outdated_reason"]) == ("outdated", "chunker_changed")


def test_documents_without_recorded_configs_are_outdated_unknown(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    doc_id = upload(client, "a.md", doc("A"))
    with db_pool.connection() as conn:
        conn.execute("update documents set chunker_config = null, embedder_config = null")

    detail = client.get(f"/admin/documents/{doc_id}").json()

    assert (detail["status"], detail["outdated_reason"]) == ("outdated", "unknown")
    assert (detail["chunker_config"], detail["embedder_config"]) == (None, None)


def test_filters_sort_and_paging_reach_the_query(client: TestClient) -> None:
    upload(client, "sellado-1.md", doc("Sellado uno"))
    upload(client, "sellado-2.md", doc("Sellado dos"))
    upload(client, "tolvas.md", doc("Limpieza de tolvas"))
    upload(client, "sellado-beta.md", doc("Sellado beta"), tenant="beta")

    page = listing(client, tenant="acme", q="SELLADO", sort="title", limit=1, offset=1)

    assert keys(page) == ["sellado-1.md"]  # "Sellado dos" < "Sellado uno"
    assert (page["total"], page["limit"], page["offset"]) == (2, 1, 1)
    assert keys(listing(client, q="50%")) == []


def test_unknown_document_is_a_404(client: TestClient) -> None:
    response = client.get("/admin/documents/upload-000000000000")

    assert response.status_code == 404
    assert response.json() == {
        "detail": [
            {"type": "document_not_found", "loc": ["path", "doc_id"], "msg": "document not found"}
        ]
    }


@pytest.mark.parametrize("doc_id", ["pro-014.md", "upload-123", "UPLOAD-0123456789ab"])
def test_malformed_doc_id_is_a_422(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/admin/documents/{doc_id}")

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == ("string_pattern_mismatch", ["path", "doc_id"])


@pytest.mark.parametrize(
    ("params", "loc", "type"),
    [
        ({"limit": 0}, ["query", "limit"], "greater_than_equal"),
        ({"limit": 101}, ["query", "limit"], "less_than_equal"),
        ({"offset": -1}, ["query", "offset"], "greater_than_equal"),
        ({"sort": "markdown"}, ["query", "sort"], "literal_error"),
        ({"sort": "-size_bytes"}, ["query", "sort"], "literal_error"),
        ({"tenant": "Acme Corp"}, ["query", "tenant"], "string_pattern_mismatch"),
        ({"q": "x" * 201}, ["query", "q"], "string_too_long"),
    ],
)
def test_invalid_query_parameters_are_a_422(
    client: TestClient, params: dict[str, Any], loc: list[str], type: str
) -> None:
    response = client.get("/admin/documents", params=params)

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == (type, loc)


def test_content_is_the_stored_markdown(client: TestClient) -> None:
    text = doc("Válvula de purga")
    doc_id = upload(client, "valvula.md", text)

    response = client.get(f"/admin/documents/{doc_id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.text == text


def test_content_comes_back_normalized(client: TestClient) -> None:
    raw = "\ufeff# Purga\r\n\r\nAbrir la válvula.\rCerrar la válvula.\r\n"
    doc_id = upload(client, "purga.md", raw)

    content = client.get(f"/admin/documents/{doc_id}/content").text
    detail = client.get(f"/admin/documents/{doc_id}").json()

    assert content == "# Purga\n\nAbrir la válvula.\nCerrar la válvula.\n"
    assert hashlib.sha256(content.encode()).hexdigest() == detail["content_hash"]


def test_content_of_an_unknown_document_is_a_json_404(client: TestClient) -> None:
    response = client.get("/admin/documents/upload-000000000000/content")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["detail"][0]["type"] == "document_not_found"


def test_content_with_a_malformed_doc_id_is_a_422(client: TestClient) -> None:
    response = client.get("/admin/documents/pro-014.md/content")

    assert response.status_code == 422
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == ("string_pattern_mismatch", ["path", "doc_id"])
