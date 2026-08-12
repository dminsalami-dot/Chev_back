from fastapi.testclient import TestClient

from chevstyle_backend.app import app


client = TestClient(app)


def test_auth_me_requires_valid_token() -> None:
    headers = {"Authorization": "Bearer test-token"}
    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["clerk_user_id"] == "user_test"
    assert body["email"] == "test@example.com"
    assert body["role"] == "customer"


def test_auth_sync_creates_user() -> None:
    headers = {"Authorization": "Bearer test-token"}
    payload = {"full_name": "Test User", "role": "customer"}

    response = client.post("/api/v1/auth/sync", json=payload, headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["clerk_user_id"] == "user_test"
    assert body["email"] == "test@example.com"
    assert body["role"] == "customer"
    assert body["full_name"] == "Test User"
    assert body["is_new_user"] is False
    assert body["convex_user_id"] == "convex_user_test"


def test_admin_guard_blocks_non_admin() -> None:
    headers = {"Authorization": "Bearer test-token"}
    response = client.get("/api/v1/auth/admin-check", headers=headers)
    assert response.status_code == 403


def test_admin_guard_allows_admin() -> None:
    headers = {"Authorization": "Bearer admin-token"}
    response = client.get("/api/v1/auth/admin-check", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_stylist_guard_allows_stylist() -> None:
    headers = {"Authorization": "Bearer stylist-token"}
    response = client.get("/api/v1/auth/stylist-check", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == "stylist"
