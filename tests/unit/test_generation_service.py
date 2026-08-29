"""Tests for services/generation_service.py — job lifecycle and fallback logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import openai

from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.services.generation_service import run_generation_job


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_image_record() -> dict:
    return {
        "_id": "img_test123",
        "user_id": "convex_user_test",
        "url": "https://mock.cdn.convex.dev/img/img_test123.jpg",
        "face_verified": True,
        "hair_segmentation_path": None,   # No SVG path → skips to Gemini directly
        "hair_bounding_box": None,
        "image_metadata": {"processed_width": 512, "processed_height": 512},
    }


def _make_hairstyle_record() -> dict:
    return {
        "_id": "style_test456",
        "name": "Low Fade",
        "imageUrl": "https://cdn.example.com/low-fade.jpg",
        "description": "A clean low fade.",
        "stylistSpecs": "2 on sides.",
    }


def _make_convex(job_id: str = "job_abc123") -> ConvexClient:
    convex = ConvexClient()
    convex.is_mock = True
    return convex


# ── Test: OpenAI success path ─────────────────────────────────────────────────

@patch("chevstyle_backend.services.generation_service._fetch_bytes")
@patch("chevstyle_backend.services.generation_service.generate_with_openai")
@patch("chevstyle_backend.services.generation_service.rasterize_hair_mask")
def test_run_generation_job_openai_success(
    mock_rasterize,
    mock_openai,
    mock_fetch,
):
    """When OpenAI succeeds, job ends as completed with model_used='openai'."""
    mock_fetch.return_value = b"fake_portrait_bytes"
    mock_rasterize.return_value = b"fake_mask_bytes"
    mock_openai.return_value = b"fake_result_png"

    convex = _make_convex()
    job_result = convex.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_test123",
        hairstyle_id="style_test456",
    )
    job_id = job_result["id"]

    image_record = _make_image_record()
    image_record["hair_segmentation_path"] = "M.5,.1 L.9,.5 L.5,.9 L.1,.5 Z"

    with patch.object(convex, "store_image", return_value="storage_result_123"), \
         patch.object(convex, "get_storage_url", return_value="https://cdn.example.com/result.png"):
        asyncio.run(
            run_generation_job(
                job_id=job_id,
                user_id="convex_user_test",
                source_image_record=image_record,
                hairstyle_record=_make_hairstyle_record(),
                convex=convex,
            )
        )

    job = convex.get_generation_job(job_id)
    assert job["status"] == "completed"
    assert job["model_used"] == "openai"
    assert job["result_url"] == "https://cdn.example.com/result.png"
    assert job["error_message"] is None


# ── Test: OpenAI 500 → Gemini fallback ───────────────────────────────────────

@patch("chevstyle_backend.services.generation_service._fetch_bytes")
@patch("chevstyle_backend.services.generation_service.generate_with_gemini")
@patch("chevstyle_backend.services.generation_service.generate_with_openai")
@patch("chevstyle_backend.services.generation_service.rasterize_hair_mask")
def test_run_generation_job_openai_fails_gemini_fallback(
    mock_rasterize,
    mock_openai,
    mock_gemini,
    mock_fetch,
):
    """When OpenAI raises APIStatusError, Gemini fallback should fire."""
    mock_fetch.return_value = b"fake_portrait_bytes"
    mock_rasterize.return_value = b"fake_mask_bytes"
    mock_openai.side_effect = openai.APIStatusError(
        "Internal Server Error",
        response=MagicMock(status_code=500, headers={}),
        body=None,
    )
    mock_gemini.return_value = b"fake_gemini_png"

    convex = _make_convex()
    job_result = convex.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_test123",
        hairstyle_id="style_test456",
    )
    job_id = job_result["id"]

    image_record = _make_image_record()
    image_record["hair_segmentation_path"] = "M.5,.1 L.9,.5 L.5,.9 L.1,.5 Z"

    with patch.object(convex, "store_image", return_value="storage_gemini_123"), \
         patch.object(convex, "get_storage_url", return_value="https://cdn.example.com/gemini_result.png"):
        asyncio.run(
            run_generation_job(
                job_id=job_id,
                user_id="convex_user_test",
                source_image_record=image_record,
                hairstyle_record=_make_hairstyle_record(),
                convex=convex,
            )
        )

    job = convex.get_generation_job(job_id)
    assert job["status"] == "completed"
    assert job["model_used"] == "gemini"
    assert job["result_url"] == "https://cdn.example.com/gemini_result.png"
    mock_gemini.assert_called_once()


# ── Test: Both engines fail → status = failed ─────────────────────────────────

@patch("chevstyle_backend.services.generation_service._fetch_bytes")
@patch("chevstyle_backend.services.generation_service.generate_with_gemini")
@patch("chevstyle_backend.services.generation_service.generate_with_openai")
@patch("chevstyle_backend.services.generation_service.rasterize_hair_mask")
def test_run_generation_job_both_fail(
    mock_rasterize,
    mock_openai,
    mock_gemini,
    mock_fetch,
):
    """When both engines fail, job should be marked as failed with an error_message."""
    mock_fetch.return_value = b"fake_portrait_bytes"
    mock_rasterize.return_value = b"fake_mask_bytes"
    mock_openai.side_effect = openai.RateLimitError(
        "Rate limit",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    mock_gemini.side_effect = RuntimeError("Gemini quota exceeded")

    convex = _make_convex()
    job_result = convex.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_test123",
        hairstyle_id="style_test456",
    )
    job_id = job_result["id"]

    image_record = _make_image_record()
    image_record["hair_segmentation_path"] = "M.5,.1 L.9,.5 L.5,.9 L.1,.5 Z"

    asyncio.run(
        run_generation_job(
            job_id=job_id,
            user_id="convex_user_test",
            source_image_record=image_record,
            hairstyle_record=_make_hairstyle_record(),
            convex=convex,
        )
    )

    job = convex.get_generation_job(job_id)
    assert job["status"] == "failed"
    assert job["error_message"] is not None
    assert "Gemini quota exceeded" in job["error_message"]


# ── Test: No SVG path → skip OpenAI, go straight to Gemini ──────────────────

@patch("chevstyle_backend.services.generation_service._fetch_bytes")
@patch("chevstyle_backend.services.generation_service.generate_with_gemini")
def test_run_generation_job_no_svg_uses_gemini(
    mock_gemini,
    mock_fetch,
):
    """With no SVG path stored, we skip OpenAI and use Gemini directly."""
    mock_fetch.return_value = b"fake_portrait_bytes"
    mock_gemini.return_value = b"fake_gemini_png"

    convex = _make_convex()
    job_result = convex.create_generation_job(
        user_id="convex_user_test",
        source_image_id="img_test123",
        hairstyle_id="style_test456",
    )
    job_id = job_result["id"]

    with patch.object(convex, "store_image", return_value="storage_xyz"), \
         patch.object(convex, "get_storage_url", return_value="https://cdn.example.com/out.png"):
        asyncio.run(
            run_generation_job(
                job_id=job_id,
                user_id="convex_user_test",
                source_image_record=_make_image_record(),  # no hair_segmentation_path
                hairstyle_record=_make_hairstyle_record(),
                convex=convex,
            )
        )

    job = convex.get_generation_job(job_id)
    assert job["status"] == "completed"
    assert job["model_used"] == "gemini"
    mock_gemini.assert_called_once()
