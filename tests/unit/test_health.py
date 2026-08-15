from fastapi.testclient import TestClient

from chevstyle_backend.app import app


client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint_returns_welcome() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to Chevstyle API", "status": "running"}
