"""The OpenAPI document: valid, complete, and served only when DOCS_ENABLED.

No database: the lifespan is not started (no `with TestClient`).
"""

from collections.abc import Iterator
from importlib.metadata import version
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from ayo_copilot.app import create_app
from ayo_copilot.ingestion.storage import TENANT_PATTERN

UPLOAD = ("/admin/documents", "post")
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return create_app(docs_enabled=True).openapi()


def operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def upload_operation(spec: dict[str, Any]) -> dict[str, Any]:
    path, method = UPLOAD
    return spec["paths"][path][method]


def resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    node: Any = spec
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return node


def test_spec_is_valid_openapi(spec: dict[str, Any]) -> None:
    validate(spec)


def test_info_comes_from_the_package(spec: dict[str, Any]) -> None:
    assert spec["info"]["title"] == "AYO Plant Copilot API"
    assert spec["info"]["version"] == version("ayo-copilot")
    assert "X-API-Key" in spec["info"]["description"]
    assert {tag["name"] for tag in spec["tags"]} == {"documents", "health"}


def test_docs_pages_are_served() -> None:
    client = TestClient(create_app(docs_enabled=True))

    for path in ("/docs", "/redoc"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
    assert client.get("/openapi.json").json()["openapi"].startswith("3.")


def test_docs_can_be_disabled() -> None:
    client = TestClient(create_app(docs_enabled=False))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    # The API itself is still there.
    assert client.get("/health").status_code == 200


def test_upload_requires_the_api_key_scheme(spec: dict[str, Any]) -> None:
    scheme = spec["components"]["securitySchemes"]["AdminApiKey"]
    assert scheme == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": scheme["description"],
    }
    assert upload_operation(spec)["security"] == [{"AdminApiKey": []}]
    assert "security" not in spec["paths"]["/health"]["get"]


def test_upload_documents_exactly_its_status_codes(spec: dict[str, Any]) -> None:
    operation = upload_operation(spec)

    assert operation["operationId"] == "upload_document"
    assert set(operation["responses"]) == {"200", "201", "401", "413", "422", "502"}
    for status, response in operation["responses"].items():
        content = response["content"]["application/json"]
        assert content["examples"], f"no example for {status}"
        name = "IngestResponse" if status in ("200", "201") else "ErrorResponse"
        assert content["schema"] == {"$ref": f"#/components/schemas/{name}"}, status
    # Ours replaces FastAPI's default, so the documented 422 is the real shape for both.
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_upload_body_is_multipart_with_described_fields(spec: dict[str, Any]) -> None:
    body = upload_operation(spec)["requestBody"]
    assert body["required"] is True
    assert set(body["content"]) == {"multipart/form-data"}

    schema = resolve(spec, body["content"]["multipart/form-data"]["schema"])
    properties = schema["properties"]
    assert set(properties) == {"file", "tenant", "title", "source_key", "force"}
    assert set(schema["required"]) == {"file", "tenant"}
    # OpenAPI 3.1's way to say "a file" (3.0 used `format: binary`).
    assert properties["file"]["contentMediaType"] == "application/octet-stream"
    assert properties["tenant"]["pattern"] == TENANT_PATTERN
    assert all(prop.get("description") for prop in properties.values())


def test_every_operation_is_documented(spec: dict[str, Any]) -> None:
    for path, method, operation in operations(spec):
        for key in ("summary", "description", "tags", "operationId"):
            assert operation.get(key), f"{method.upper()} {path} has no {key}"


def test_every_schema_property_is_described(spec: dict[str, Any]) -> None:
    for name, schema in spec["components"]["schemas"].items():
        for prop, definition in schema.get("properties", {}).items():
            assert definition.get("description"), f"components.schemas.{name}.{prop}"
