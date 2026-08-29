"""Tests for routers/previews.py — generate, poll, list, ownership."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from chevstyle_backend.app import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer test-token"}


def _mock_convex():
    """Return a ConvexClient configured in mock mode with helpers stubbed."""
    from chevstyle_backend.convex.client import ConvexClient
    c = ConvexClient()
    c.is_mock = True
    return c


# ── POST /api/v1/previews/generate ───────────────────────────────────────────

@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_generate_preview_returns_202(mock_convex_cls):
    """POST /generate should return 202 with a preview_id."""
    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c

    # Stub hairstyle lookup
    mock_c.get_hairstyle_by_id = MagicMock(
        return_value={
            "_id": "style_001",
            "name": "Low Fade",
            "imageUrl": "https://cdn.example.com/low-fade.jpg",
            "description": "A clean fade.",
            "stylistSpecs": "Taper with 2 guard.",
        }
    )

    response = client.post(
        "/api/v1/previews/generate",
        json={"image_id": "img_001", "hairstyle_id": "style_001"},
        headers=HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert "preview_id" in body
    assert body["status"] == "queued"
    assert body["hairstyle_id"] == "style_001"
    assert body["hairstyle_name"] == "Low Fade"
    assert body["image_id"] == "img_001"


@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_generate_preview_hairstyle_not_found_returns_404(mock_convex_cls):
    """If hairstyle_id doesn't exist, 404 should be returned."""
    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c
    mock_c.get_hairstyle_by_id = MagicMock(return_value=None)

    response = client.post(
        "/api/v1/previews/generate",
        json={"image_id": "img_001", "hairstyle_id": "nonexistent_style"},
        headers=HEADERS,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "HAIRSTYLE_NOT_FOUND"


# ── GET /api/v1/previews/{preview_id} ────────────────────────────────────────

@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_get_preview_status_returns_job(mock_convex_cls):
    """GET /{preview_id} should return job status for the owning user."""
    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c

    # Pre-create a job in the mock store
    job_result = mock_c.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_001",
        hairstyle_id="style_001",
    )
    job_id = job_result["id"]

    mock_c.get_hairstyle_by_id = MagicMock(
        return_value={"_id": "style_001", "name": "Low Fade"}
    )

    response = client.get(f"/api/v1/previews/{job_id}", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["preview_id"] == job_id
    assert body["status"] == "queued"
    assert body["hairstyle_id"] == "style_001"


@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_get_preview_status_wrong_user_returns_403(mock_convex_cls):
    """GET /{preview_id} should return 403 if job belongs to a different user."""
    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c

    # Create job for a DIFFERENT user
    job_result = mock_c.create_generation_job(
        user_id="different_user_id",
        source_image_id="img_999",
        hairstyle_id="style_001",
    )
    job_id = job_result["id"]

    response = client.get(f"/api/v1/previews/{job_id}", headers=HEADERS)

    # Our test token user is "convex_user_test", not "different_user_id"
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN"


@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_get_preview_status_not_found_returns_404(mock_convex_cls):
    """GET /{preview_id} for nonexistent job should return 404."""
    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c

    response = client.get("/api/v1/previews/nonexistent_job_id", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "PREVIEW_NOT_FOUND"


# ── GET /api/v1/previews ──────────────────────────────────────────────────────

@patch("chevstyle_backend.routers.previews.ConvexClient")
def test_list_previews_returns_user_jobs(mock_convex_cls):
    """GET /previews should return all jobs for the authenticated user."""
    import chevstyle_backend.convex.client as convex_module
    # Clear the shared in-memory store to ensure test isolation
    with convex_module._lock:
        convex_module._generation_job_store.clear()

    mock_c = _mock_convex()
    mock_convex_cls.return_value = mock_c
    mock_c.get_hairstyle_by_id = MagicMock(return_value={"_id": "s1", "name": "Afro"})

    # Create 2 jobs for this user
    mock_c.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_001",
        hairstyle_id="s1",
    )
    mock_c.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_002",
        hairstyle_id="s1",
    )
    # Create 1 job for another user (should NOT appear)
    mock_c.create_generation_job(
        user_id="other_user",
        source_image_id="img_003",
        hairstyle_id="s1",
    )

    response = client.get("/api/v1/previews", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["previews"]) == 2
