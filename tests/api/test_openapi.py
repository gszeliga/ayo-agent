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
from ayo_copilot.db.repository import SORT_KEYS
from ayo_copilot.ingestion.signatures import DOC_ID_PATTERN
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


@pytest.mark.parametrize(
    ("path", "operation_id", "statuses", "model"),
    [
        ("/admin/documents", "list_documents", {"200", "401", "422"}, "DocumentPage"),
        (
            "/admin/documents/{doc_id}",
            "get_document",
            {"200", "401", "404", "422"},
            "Document",
        ),
        (
            "/admin/documents/{doc_id}/chunks",
            "list_document_chunks",
            {"200", "401", "404", "422"},
            "ChunkPage",
        ),
    ],
)
def test_read_operations_document_exactly_their_status_codes(
    spec: dict[str, Any], path: str, operation_id: str, statuses: set[str], model: str
) -> None:
    operation = spec["paths"][path]["get"]

    assert operation["operationId"] == operation_id
    assert operation["security"] == [{"AdminApiKey": []}]
    assert set(operation["responses"]) == statuses
    for status, response in operation["responses"].items():
        content = response["content"]["application/json"]
        assert content["examples"], f"no example for {status}"
        name = model if status == "200" else "ErrorResponse"
        assert content["schema"] == {"$ref": f"#/components/schemas/{name}"}, status


def test_content_operation_documents_markdown_and_json_errors(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/admin/documents/{doc_id}/content"]["get"]

    assert operation["operationId"] == "get_document_content"
    assert operation["security"] == [{"AdminApiKey": []}]
    assert set(operation["responses"]) == {"200", "401", "404", "422"}
    responses = operation["responses"]
    (media_type,) = responses["200"]["content"]
    assert media_type == "text/markdown; charset=utf-8"
    markdown = responses["200"]["content"][media_type]
    assert markdown["schema"] == {"type": "string"}
    assert markdown["examples"]
    for status in ("401", "404", "422"):
        (content,) = responses[status]["content"].values()
        assert set(responses[status]["content"]) == {"application/json"}, status
        assert content["examples"], f"no example for {status}"
        assert content["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}, status


def test_list_parameters_are_described_with_their_bounds(spec: dict[str, Any]) -> None:
    parameters = {p["name"]: p for p in spec["paths"]["/admin/documents"]["get"]["parameters"]}

    assert set(parameters) == {"tenant", "q", "sort", "limit", "offset"}
    assert all(p["description"] and p["in"] == "query" for p in parameters.values())
    assert set(parameters["sort"]["schema"]["enum"]) == {
        f"{prefix}{key}" for key in SORT_KEYS for prefix in ("", "-")
    }
    assert parameters["sort"]["schema"]["default"] == "-updated_at"
    assert (parameters["limit"]["schema"]["minimum"], parameters["limit"]["schema"]["maximum"]) == (
        1,
        100,
    )
    assert parameters["offset"]["schema"]["minimum"] == 0


def test_doc_id_path_parameter_has_the_id_pattern(spec: dict[str, Any]) -> None:
    (parameter,) = spec["paths"]["/admin/documents/{doc_id}"]["get"]["parameters"]

    assert parameter["schema"]["pattern"] == DOC_ID_PATTERN
    assert parameter["description"]


def test_page_schemas_have_clean_names(spec: dict[str, Any]) -> None:
    names = set(spec["components"]["schemas"])

    assert {"DocumentPage", "Document", "ChunkPage", "Chunk"} <= names
    assert not names & {"DocumentSummary", "DocumentDetail"}
    assert not [name for name in names if "[" in name or name.startswith("Page")]


def test_nullable_document_fields_are_declared_nullable(spec: dict[str, Any]) -> None:
    properties = spec["components"]["schemas"]["Document"]["properties"]
    nullable = {
        name for name, schema in properties.items() if {"type": "null"} in schema.get("anyOf", [])
    }

    assert nullable == {
        "title",
        "outdated_reason",
        "size_bytes",
        "chunked_at",
        "embedded_at",
        "chunker_config",
        "embedder_config",
    }


def test_chunk_parameters_are_described_with_their_bounds(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/admin/documents/{doc_id}/chunks"]["get"]
    parameters = {p["name"]: p for p in operation["parameters"]}

    assert set(parameters) == {"doc_id", "limit", "offset", "include_embedding"}
    assert all(p["description"] for p in parameters.values())
    assert parameters["doc_id"]["schema"]["pattern"] == DOC_ID_PATTERN
    limit = parameters["limit"]["schema"]
    assert (limit["minimum"], limit["maximum"], limit["default"]) == (1, 200, 50)
    include_embedding = parameters["include_embedding"]["schema"]
    assert (include_embedding["type"], include_embedding["default"]) == ("boolean", False)


def test_chunk_embedding_is_declared_nullable(spec: dict[str, Any]) -> None:
    properties = spec["components"]["schemas"]["Chunk"]["properties"]

    assert {"type": "null"} in properties["embedding"]["anyOf"]
    assert {"type": "null"} in properties["heading"]["anyOf"]
