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
            "has_completed_onboarding": True,
            "style_preferences": ["fade"],
        },
    )


def test_convex_client_upsert_user_includes_full_name() -> None:
    from unittest.mock import MagicMock
    from chevstyle_backend.convex.client import ConvexClient

    client = ConvexClient(url="https://fake-convex.cloud")
    client.is_mock = False
    client.real_client = MagicMock()
    client.real_client.mutation.return_value = {
        "id": "convex_123",
        "is_new": True,
        "record": {"clerk_user_id": "user_123", "email": "test@example.com", "role": "customer", "full_name": None},
    }

    client.upsert_user(
        clerk_user_id="user_123",
        email="test@example.com",
        role="customer",
        full_name=None,
    )

    client.real_client.mutation.assert_called_once_with(
        "users:upsert_user",
        {
            "clerk_user_id": "user_123",
            "email": "test@example.com",
            "role": "customer",
            "full_name": None,
        },
    )




def test_auth_patch_partial_preserves_existing_fields() -> None:
    headers = {"Authorization": "Bearer test-token"}
    # 1. Sync full profile initially
    sync_payload = {
        "full_name": "Original Name",
        "role": "customer",
        "gender": "men",
        "style_preferences": ["fade"],
    }
    sync_res = client.post("/api/v1/auth/sync", json=sync_payload, headers=headers)
    assert sync_res.status_code == 200

    # 2. Patch only style preferences (no full_name, no notification_prefs)
    patch_payload = {
        "style_preferences": ["fade", "buzz"],
    }
    patch_res = client.patch("/api/v1/auth/me", json=patch_payload, headers=headers)
    assert patch_res.status_code == 200

    # 3. Verify full_name and gender are completely preserved and NOT unset
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_body = me_res.json()
    assert me_body["full_name"] == "Original Name"
    assert me_body["gender"] == "men"
    assert me_body["style_preferences"] == ["fade", "buzz"]
    # notification_prefs was not modified by patch (remains what was previously set)
    assert me_body["notification_prefs"] == {"generation_complete": False}
