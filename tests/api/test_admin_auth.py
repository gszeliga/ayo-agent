"""Every route under /admin needs the key, so a new endpoint can't be left unprotected.

Routes are read from the OpenAPI document: FastAPI 0.148 wraps included routers in a
private class, so `app.routes` no longer lists them. A route hidden from the schema
(`include_in_schema=False`) would escape this test; don't hide /admin routes.
"""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings

pytestmark = pytest.mark.integration

# A well-formed id, so path validation can't answer before authentication.
PATH_VALUES = {"doc_id": "upload-000000000000"}


def admin_routes() -> list[tuple[str, str]]:
    paths = create_app(docs_enabled=True).openapi()["paths"]
    routes = [
        (method.upper(), path)
        for path, item in paths.items()
        if path.startswith("/admin")
        for method in sorted(item)
    ]
    assert routes, "no /admin routes found"
    return routes


def concrete(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: PATH_VALUES[m.group(1)], path)


@pytest.fixture(scope="module")
def client(migrated_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        allow_remote_database=True,
        admin_api_key="test-admin-key",
        embedding_provider="fake",
    )
    with TestClient(create_app(settings, docs_enabled=True)) as client:
        yield client


@pytest.mark.parametrize(("method", "path"), admin_routes())
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}], ids=["missing", "wrong"])
def test_admin_route_requires_the_key(
    client: TestClient, db_pool: ConnectionPool, method: str, path: str, headers: dict
) -> None:
    response = client.request(method, concrete(path), headers=headers)

    assert response.status_code == 401, response.text
    assert response.json()["detail"][0]["type"] == "invalid_api_key"
