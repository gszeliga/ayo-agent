"""CORS for a browser UI on another origin. No database: preflights, `/health` and an error
response are enough."""

import pytest
from fastapi.testclient import TestClient

from ayo_copilot import app as app_module
from ayo_copilot.app import create_app
from ayo_copilot.config import BuildSettings, Settings

UI = "http://localhost:5173"
OTHER = "https://evil.example.com"


def make_client(**overrides: object) -> TestClient:
    settings = Settings(
        _env_file=None, admin_api_key="test-admin-key", embedding_provider="fake", **overrides
    )
    # No `with`: the lifespan (and so the database) is not started.
    return TestClient(create_app(settings, docs_enabled=True))


def preflight(client: TestClient, origin: str, method: str = "DELETE"):
    return client.options(
        "/admin/documents/upload-1890b5dc5335",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "x-api-key, content-type",
        },
    )


def cors_headers(response) -> set[str]:
    return {name for name in response.headers if name.startswith("access-control-")}


@pytest.fixture
def client() -> TestClient:
    return make_client(cors_allowed_origins=UI)


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_preflight_from_an_allowed_origin_succeeds(client: TestClient, method: str) -> None:
    response = preflight(client, UI, method)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == UI
    assert method in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-api-key" in allowed_headers and "content-type" in allowed_headers
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_for_an_unlisted_method_fails(client: TestClient) -> None:
    response = preflight(client, UI, "PUT")

    assert response.status_code == 400


def test_allowed_origin_can_read_answers_and_errors(client: TestClient) -> None:
    ok = client.get("/health", headers={"Origin": UI})
    error = client.get("/admin/nothing-here", headers={"Origin": UI})

    assert ok.headers["access-control-allow-origin"] == UI
    assert error.status_code == 404
    assert error.json()["detail"][0]["type"]
    assert error.headers["access-control-allow-origin"] == UI


def test_disallowed_origin_gets_no_cors_headers(client: TestClient) -> None:
    refused = preflight(client, OTHER)
    response = client.get("/health", headers={"Origin": OTHER})

    assert refused.status_code == 400
    assert "access-control-allow-origin" not in refused.headers
    assert response.status_code == 200
    assert cors_headers(response) == set()


def test_cors_is_off_by_default() -> None:
    client = make_client()

    response = client.get("/health", headers={"Origin": UI})

    assert cors_headers(response) == set()
    assert cors_headers(preflight(client, UI)) == set()


def test_building_with_docs_enabled_alone_ignores_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", UI)
    client = TestClient(create_app(docs_enabled=True))

    assert cors_headers(client.get("/health", headers={"Origin": UI})) == set()


def test_building_from_the_environment_reads_the_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", UI)
    # Never the real `.env`: only the environment set here.
    monkeypatch.setattr(app_module, "BuildSettings", lambda: BuildSettings(_env_file=None))
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": UI})

    assert response.headers["access-control-allow-origin"] == UI
