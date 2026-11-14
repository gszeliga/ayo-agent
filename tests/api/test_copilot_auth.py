"""Every route under /copilot needs the key (decision 9), read from the OpenAPI document
like the /admin test: a new copilot endpoint can't be left unprotected."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings

pytestmark = pytest.mark.integration

# Well-formed values, so validation can't answer before authentication.
PATH_VALUES = {"session_id": "3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14"}
BODY = {
    "session_id": "3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14",
    "tenant": "cliente-acme",
    "text": "Hola",
}


def copilot_routes() -> list[tuple[str, str]]:
    paths = create_app(docs_enabled=True).openapi()["paths"]
    routes = [
        (method.upper(), path)
        for path, item in paths.items()
        if path.startswith("/copilot")
        for method in sorted(item)
    ]
    assert routes, "no /copilot routes found"
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


@pytest.mark.parametrize(("method", "path"), copilot_routes())
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}], ids=["missing", "wrong"])
def test_copilot_route_requires_the_key(
    client: TestClient, db_pool: ConnectionPool, method: str, path: str, headers: dict
) -> None:
    body = BODY if method == "POST" else None
    response = client.request(method, concrete(path), headers=headers, json=body)

    assert response.status_code == 401, response.text
    assert response.json()["detail"][0]["type"] == "invalid_api_key"
    with db_pool.connection() as conn:
        assert conn.execute("select count(*) from problems").fetchone() == (0,)
