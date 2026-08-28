from unittest.mock import AsyncMock, patch
import pytest
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


def test_auth_update_me_changes_profile() -> None:
    headers = {"Authorization": "Bearer test-token"}
    payload = {
        "full_name": "Updated User",
        "notification_prefs": {"generation_complete": False},
    }

    response = client.patch("/api/v1/auth/me", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"updated": True}

    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated User"
    assert body["notification_prefs"]["generation_complete"] is False


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


@pytest.mark.anyio
@patch("chevstyle_backend.auth.clerk._fetch_jwks")
@patch("chevstyle_backend.auth.clerk._find_jwk_for_token")
@patch("chevstyle_backend.auth.clerk.jwt.decode")
@patch("chevstyle_backend.auth.clerk.settings")
@patch("chevstyle_backend.auth.clerk.ConvexClient")
async def test_verify_clerk_jwt_role_null(
    mock_convex_client, mock_settings, mock_decode, mock_find_jwk, mock_fetch_jwks
) -> None:
    mock_settings.clerk_jwks_url = "http://mock-jwks"
    mock_settings.app_env = "production"
    mock_settings.clerk_audience = None
    mock_settings.clerk_issuer = None

    mock_decode.return_value = {
        "sub": "user_123",
        "email": "user@example.com",
        "name": "User Name",
        "role": None,
    }

    mock_convex = mock_convex_client.return_value
    mock_convex.upsert_user.return_value = (
        "convex_123",
        True,
        {
            "created_at": "2026-08-13T14:59:54Z",
            "full_name": "User Name",
        },
    )

    from chevstyle_backend.auth.clerk import verify_clerk_jwt
    user = await verify_clerk_jwt("some-token")

    assert user.clerk_user_id == "user_123"
    assert user.email == "user@example.com"
    assert user.role == "customer"
    assert user.full_name == "User Name"



def test_auth_sync_with_gender_and_preferences() -> None:
    headers = {"Authorization": "Bearer test-token"}
    payload = {
        "full_name": "Style User",
        "role": "customer",
        "gender": "men",
        "style_preferences": ["fade", "short"],
    }

    response = client.post("/api/v1/auth/sync", json=payload, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["gender"] == "men"
    assert body["style_preferences"] == ["fade", "short"]
    assert body["has_completed_onboarding"] is True


def test_auth_update_me_style_profile() -> None:
    headers = {"Authorization": "Bearer test-token"}
    payload = {
        "gender": "women",
        "style_preferences": ["bob", "layers"],
        "has_completed_onboarding": True,
    }

    response = client.patch("/api/v1/auth/me", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"updated": True}

    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["gender"] == "women"
    assert body["style_preferences"] == ["bob", "layers"]
    assert body["has_completed_onboarding"] is True


def test_convex_client_update_user_profile_payload_excludes_none() -> None:
    from unittest.mock import MagicMock
    from chevstyle_backend.convex.client import ConvexClient

    client = ConvexClient(url="https://fake-convex.cloud")
    client.is_mock = False
    client.real_client = MagicMock()
    client.real_client.mutation.return_value = {"updated": True, "record": {"clerk_user_id": "test_user"}}

    client.update_user_profile(
        clerk_user_id="test_user",
        gender="men",
        style_preferences=["fade"],
    )

    client.real_client.mutation.assert_called_once_with(
        "users:update_user_profile",
        {
            "clerk_user_id": "test_user",
            "gender": "men",
            "stylePreferences": ["fade"],
        },
    )

