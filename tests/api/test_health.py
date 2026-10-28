from fastapi.testclient import TestClient

from ayo_copilot.app import create_app


def test_health_returns_ok_without_a_database() -> None:
    # No `with`: the lifespan (and so the database) is not started.
    client = TestClient(create_app(docs_enabled=True))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
