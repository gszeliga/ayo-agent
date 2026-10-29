"""Contract: every response each operation documents is triggered for real, and its body
validates against the schema documented for that status.

The schemas are made strict (`additionalProperties: false`) for the check, so a body
with an undocumented field fails too.
"""

import copy
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openapi_schema_validator import OAS31Validator
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.dependencies import get_embedder
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pro-014-control-sellado.md"
API_KEY = "test-admin-key"
MAX_UPLOAD_BYTES = 1000


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("provider returned HTTP 503")


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str):
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        # testcontainers may report a Docker host other than localhost.
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
        max_upload_bytes=MAX_UPLOAD_BYTES,
    )
    app = create_app(settings, docs_enabled=True)
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def strict_spec() -> dict[str, Any]:
    spec = copy.deepcopy(create_app(docs_enabled=True).openapi())
    for schema in spec["components"]["schemas"].values():
        if "properties" in schema:
            schema.setdefault("additionalProperties", False)
    return spec


UPLOAD = ("post", "/admin/documents")
LIST = ("get", "/admin/documents")
GET = ("get", "/admin/documents/{doc_id}")


def documented_schema(
    spec: dict[str, Any], status: int, operation: tuple[str, str] = UPLOAD
) -> dict[str, Any]:
    method, path = operation
    response = spec["paths"][path][method]["responses"][str(status)]
    schema = response["content"]["application/json"]["schema"]
    # Root-relative `$ref`s resolve against the components carried along.
    return {**schema, "components": spec["components"]}


def post(client: TestClient, content: bytes, filename: str = "pro-014.md", **kwargs: Any):
    headers = kwargs.pop("headers", {"X-API-Key": API_KEY})
    data = kwargs.pop("data", {"tenant": "acme"})
    return client.post(
        "/admin/documents",
        files={"file": (filename, content, "text/markdown")},
        data=data,
        headers=headers,
    )


SMALL_DOC = "# Sellado\n\nComprobar la presión de la junta antes de cada turno.\n".encode()


def get(client: TestClient, url: str, headers: dict[str, str] | None = None, **params: Any):
    return client.get(
        url, params=params, headers={"X-API-Key": API_KEY} if headers is None else headers
    )


def get_uploaded(client: TestClient):
    doc_id = post(client, SMALL_DOC).json()["doc_id"]
    return get(client, f"/admin/documents/{doc_id}")


# name -> (operation, expected status, how to trigger it)
CASES = {
    "upload 201 indexed": (UPLOAD, 201, lambda c: post(c, SMALL_DOC)),
    "upload 200 up_to_date": (UPLOAD, 200, lambda c: (post(c, SMALL_DOC), post(c, SMALL_DOC))[1]),
    "upload 401 no key": (UPLOAD, 401, lambda c: post(c, SMALL_DOC, headers={})),
    "upload 413 too large": (
        UPLOAD,
        413,
        lambda c: post(c, b"# T\n\n" + b"a" * (MAX_UPLOAD_BYTES + 1)),
    ),
    "upload 422 FastAPI missing field": (UPLOAD, 422, lambda c: post(c, SMALL_DOC, data={})),
    "upload 422 FastAPI pattern": (
        UPLOAD,
        422,
        lambda c: post(c, SMALL_DOC, data={"tenant": "Acme Corp"}),
    ),
    "upload 422 ours not UTF-8": (UPLOAD, 422, lambda c: post(c, "# Señal\n".encode("latin-1"))),
    "upload 422 ours extension": (UPLOAD, 422, lambda c: post(c, SMALL_DOC, filename="notas.txt")),
    "list 200 empty": (LIST, 200, lambda c: get(c, "/admin/documents")),
    "list 200 items": (LIST, 200, lambda c: (post(c, SMALL_DOC), get(c, "/admin/documents"))[1]),
    "list 401 no key": (LIST, 401, lambda c: get(c, "/admin/documents", headers={})),
    "list 422 sort": (LIST, 422, lambda c: get(c, "/admin/documents", sort="size")),
    "list 422 limit": (LIST, 422, lambda c: get(c, "/admin/documents", limit=500)),
    "get 200": (GET, 200, get_uploaded),
    "get 401 no key": (
        GET,
        401,
        lambda c: get(c, "/admin/documents/upload-000000000000", headers={}),
    ),
    "get 404": (GET, 404, lambda c: get(c, "/admin/documents/upload-000000000000")),
    "get 422 malformed id": (GET, 422, lambda c: get(c, "/admin/documents/pro-014.md")),
}
# Triggered by dedicated tests below.
EXTRA_TRIGGERED = {UPLOAD: {502}}


@pytest.mark.parametrize("case", CASES)
def test_response_matches_its_documented_schema(
    client: TestClient, strict_spec: dict[str, Any], case: str
) -> None:
    operation, status, trigger = CASES[case]

    response = trigger(client)

    assert response.status_code == status, response.text
    OAS31Validator(documented_schema(strict_spec, status, operation)).validate(response.json())


def test_provider_failure_matches_its_documented_schema(
    client: TestClient, strict_spec: dict[str, Any]
) -> None:
    client.app.dependency_overrides[get_embedder] = FailingEmbedder

    response = post(client, SMALL_DOC)

    assert response.status_code == 502
    OAS31Validator(documented_schema(strict_spec, 502)).validate(response.json())


@pytest.mark.parametrize("operation", [UPLOAD, LIST, GET], ids=lambda op: " ".join(op))
def test_every_documented_status_is_triggered(
    strict_spec: dict[str, Any], operation: tuple[str, str]
) -> None:
    method, path = operation
    documented = {int(s) for s in strict_spec["paths"][path][method]["responses"]}
    triggered = {status for op, status, _ in CASES.values() if op == operation}

    assert triggered | EXTRA_TRIGGERED.get(operation, set()) == documented


def test_every_admin_operation_has_contract_cases(strict_spec: dict[str, Any]) -> None:
    documented = {
        (method, path)
        for path, item in strict_spec["paths"].items()
        if path.startswith("/admin")
        for method in item
    }

    assert documented == {UPLOAD, LIST, GET}


def test_strict_schemas_reject_undocumented_fields(strict_spec: dict[str, Any]) -> None:
    # The check above would be toothless if extra fields were allowed.
    body = {"detail": [{"type": "x", "loc": [], "msg": "m", "surprise": 1}]}

    assert not OAS31Validator(documented_schema(strict_spec, 422)).is_valid(body)


def test_fake_embedder_is_used(client: TestClient) -> None:
    # Guards the fixture: no case above may reach a real provider.
    assert isinstance(client.app_state["embedder"], FakeEmbedder)
