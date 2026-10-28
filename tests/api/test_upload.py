import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.db.repository import similar_chunks
from ayo_copilot.dependencies import get_embedder
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.signatures import make_doc_id

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pro-014-control-sellado.md"
CONTENT = FIXTURE.read_bytes()
FILENAME = "pro-014-control-sellado.md"
API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
# Marks content that must never come back in an error body.
SECRET_TEXT = "Contenido confidencial de la planta"


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("provider returned HTTP 503")


def make_app(database_url: str, **overrides: object) -> FastAPI:
    values: dict[str, object] = {
        "database_url": database_url,
        # testcontainers may report a Docker host other than localhost.
        "allow_remote_database": True,
        "admin_api_key": API_KEY,
        "embedding_provider": "fake",
    }
    values.update(overrides)
    return create_app(Settings(_env_file=None, **values))


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimensions=1024)


@pytest.fixture
def app(db_pool: ConnectionPool, migrated_database_url: str, embedder: FakeEmbedder):
    # `db_pool` empties the tables of the database the app uses.
    app = make_app(migrated_database_url)
    app.dependency_overrides[get_embedder] = lambda: embedder
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def upload(
    client: TestClient,
    content: bytes = CONTENT,
    *,
    filename: str = FILENAME,
    headers: dict[str, str] | None = None,
    **fields: str,
):
    data = {"tenant": "acme", **fields}
    return client.post(
        "/admin/documents",
        files={"file": (filename, content, "text/markdown")},
        data=data,
        headers=HEADERS if headers is None else headers,
    )


def assert_error(response, status: int, type: str, loc: list[str | int]) -> dict:
    assert response.status_code == status
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert len(detail) == 1
    item = detail[0]
    assert item["type"] == type
    assert item["loc"] == loc
    assert isinstance(item["msg"], str)
    assert item["msg"]
    return item


def document_count(pool: ConnectionPool) -> int:
    with pool.connection() as conn:
        return conn.execute("select count(*) from documents").fetchone()[0]


# --- success ---


def test_first_upload_is_indexed(client: TestClient, db_pool: ConnectionPool) -> None:
    response = upload(client)

    assert response.status_code == 201
    body = response.json()
    assert body["doc_id"] == make_doc_id("acme", FILENAME)
    assert body["status"] == "indexed"
    assert body["chunk_count"] > 0
    assert body["embedding_model"] == "voyage-4"
    assert len(body["embed_signature"]) == 12
    assert document_count(db_pool) == 1


def test_same_upload_is_up_to_date_without_a_provider_call(
    client: TestClient, embedder: FakeEmbedder
) -> None:
    first = upload(client).json()

    response = upload(client)

    assert response.status_code == 200
    assert response.json() == {"doc_id": first["doc_id"], "status": "up_to_date"}
    assert len(embedder.calls) == 1


def test_force_reindexes(client: TestClient, embedder: FakeEmbedder) -> None:
    upload(client)

    response = upload(client, force="true")

    assert response.status_code == 201
    assert response.json()["status"] == "indexed"
    assert len(embedder.calls) == 2


def test_extension_check_ignores_case(client: TestClient) -> None:
    assert upload(client, filename="PRO-014.MD").status_code == 201


def test_given_source_key_and_title_are_used(client: TestClient) -> None:
    response = upload(client, source_key="docs/sellado.md", title="Sellado")

    assert response.status_code == 201
    assert response.json()["doc_id"] == make_doc_id("acme", "sellado.md")


def test_an_uploaded_section_can_be_found_by_similarity(
    client: TestClient, db_pool: ConnectionPool, embedder: FakeEmbedder
) -> None:
    # End to end through HTTP: upload the multi-section fixture, then query its vectors.
    doc_id = upload(client).json()["doc_id"]
    [sent] = embedder.calls
    target = next(text for text in sent if "Presión" in text)
    [query] = FakeEmbedder(dimensions=1024).embed_documents([target])

    with db_pool.connection() as conn:
        best, *_ = similar_chunks(conn, tenant="acme", embedding=query, limit=3)
        other_tenant = similar_chunks(conn, tenant="other", embedding=query, limit=3)

    assert best.doc_id == doc_id
    assert best.heading == "PRO-014 Control de sellado > 3. Pasos > 3.2 Medición"
    assert "Presión" in best.chunk_text
    assert best.distance == pytest.approx(0, abs=1e-6)
    assert other_tenant == []


# --- authentication ---


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": ""}, {"X-API-Key": "wrong"}, {"X-API-Key": "clé-erronée"}],
    ids=["missing", "empty", "wrong", "non-ascii"],
)
def test_upload_requires_the_admin_key(
    client: TestClient,
    db_pool: ConnectionPool,
    embedder: FakeEmbedder,
    headers: dict[str, str],
) -> None:
    # httpx encodes str headers as ASCII; send the non-ASCII one as UTF-8 bytes.
    raw = {k: v.encode() for k, v in headers.items()}

    response = upload(client, headers=raw)

    assert_error(response, 401, "invalid_api_key", ["header", "x-api-key"])
    assert response.headers["www-authenticate"] == "APIKey"
    assert len(embedder.calls) == 0
    assert document_count(db_pool) == 0


# --- size limit ---


def test_too_large_content_length_is_rejected_before_parsing(
    migrated_database_url: str, db_pool: ConnectionPool
) -> None:
    app = make_app(migrated_database_url, max_upload_bytes=1000)

    with TestClient(app) as client:
        response = upload(client, b"# T\n\n" + b"a" * 100_000)

    assert_error(response, 413, "file_too_large", ["body", "file"])
    assert document_count(db_pool) == 0


def test_too_large_file_is_rejected_when_read(
    migrated_database_url: str, db_pool: ConnectionPool
) -> None:
    # Content-Length is within the multipart allowance, so the read limit applies.
    app = make_app(migrated_database_url, max_upload_bytes=1000)

    with TestClient(app) as client:
        response = upload(client, b"# T\n\n" + b"a" * 1000)
        at_limit = upload(client, b"# T\n\n" + b"a" * 995)

    assert_error(response, 413, "file_too_large", ["body", "file"])
    assert at_limit.status_code == 201


# --- invalid input ---


@pytest.mark.parametrize(
    ("content", "filename", "type"),
    [
        (f"# {SECRET_TEXT}\n".encode(), "notas.txt", "file_extension"),
        (f"# {SECRET_TEXT}\n".encode(), "sin-extension", "file_extension"),
        (b"   \n\n", FILENAME, "file_empty"),
        (f"# {SECRET_TEXT}\n".encode("utf-16"), FILENAME, "file_encoding"),
        (f"# {SECRET_TEXT}\n\n---\n\n- 4 -\n".encode(), FILENAME, "file_no_content"),
    ],
)
def test_invalid_files_are_rejected(
    client: TestClient,
    db_pool: ConnectionPool,
    embedder: FakeEmbedder,
    content: bytes,
    filename: str,
    type: str,
) -> None:
    response = upload(client, content, filename=filename)

    item = assert_error(response, 422, type, ["body", "file"])
    assert "input" not in item
    assert SECRET_TEXT not in response.text
    assert len(embedder.calls) == 0
    assert document_count(db_pool) == 0


def test_invalid_tenant_is_rejected_by_the_schema(
    client: TestClient, embedder: FakeEmbedder
) -> None:
    # The pattern is in the OpenAPI schema, so FastAPI checks it before our code.
    response = upload(client, tenant="Acme Corp")

    item = assert_error(response, 422, "string_pattern_mismatch", ["body", "tenant"])
    assert item["input"] == "Acme Corp"
    assert len(embedder.calls) == 0


@pytest.mark.parametrize("tenant", ["acme\n", "a"])
def test_schema_pattern_is_as_strict_as_the_service(client: TestClient, tenant: str) -> None:
    # pydantic's regex engine differs from `re`: check a trailing newline and the length.
    assert upload(client, tenant=tenant).status_code == 422


def test_invalid_source_key_points_at_the_field(client: TestClient) -> None:
    response = upload(client, source_key="docs/..")

    assert_error(response, 422, "source_key_invalid", ["body", "source_key"])


def test_invalid_derived_source_key_points_at_the_file(client: TestClient) -> None:
    # No source_key: it comes from the file name, so the file is at fault.
    response = upload(client, filename="x" * 300 + ".md")

    assert_error(response, 422, "source_key_invalid", ["body", "file"])


def test_fastapi_validation_errors_share_the_shape(client: TestClient) -> None:
    response = client.post(
        "/admin/documents",
        files={"file": (FILENAME, CONTENT, "text/markdown")},
        data={"force": "maybe"},
        headers=HEADERS,
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert {(item["type"], tuple(item["loc"])) for item in detail} == {
        ("missing", ("body", "tenant")),
        ("bool_parsing", ("body", "force")),
    }
    assert all(isinstance(item["msg"], str) for item in detail)


# --- provider failure ---


def test_provider_failure_is_a_502_and_stores_nothing(
    app: FastAPI, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    app.dependency_overrides[get_embedder] = FailingEmbedder

    with TestClient(app) as client:
        response = upload(client, f"# T\n\n{SECRET_TEXT}, sección con contenido.\n".encode())

    item = assert_error(response, 502, "embedding_failed", [])
    assert "503" not in item["msg"]
    assert "HTTP 503" in caplog.text
    assert SECRET_TEXT not in caplog.text
    assert document_count(db_pool) == 0


# --- framework errors ---


def test_unknown_path_is_a_404(client: TestClient) -> None:
    assert_error(client.get("/nope"), 404, "not_found", [])


def test_wrong_method_is_a_405(client: TestClient) -> None:
    response = client.get("/admin/documents", headers=HEADERS)

    assert_error(response, 405, "method_not_allowed", [])
    assert response.headers["allow"] == "POST"


def test_malformed_multipart_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/admin/documents",
        content=b"garbage",
        headers={**HEADERS, "Content-Type": "multipart/form-data"},  # no boundary
    )

    assert_error(response, 400, "bad_request", [])


def test_unhandled_errors_are_a_json_500(
    migrated_database_url: str, db_pool: ConnectionPool
) -> None:
    app = make_app(migrated_database_url)

    @app.get("/boom")
    def boom():
        raise RuntimeError(f"secret detail: {SECRET_TEXT}")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert_error(response, 500, "internal_error", [])
    assert SECRET_TEXT not in response.text


def test_errors_are_logged_without_content(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    upload(client, f"# {SECRET_TEXT}\n".encode(), filename="notas.txt")
    upload(client, f"# T\n\n{SECRET_TEXT}, sección con contenido.\n".encode())

    assert SECRET_TEXT not in caplog.text
