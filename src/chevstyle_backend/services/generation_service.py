"""
generation_service.py
---------------------
Orchestrates a full hairstyle-swap generation job:

  1. Set job status → processing
  2. Fetch portrait bytes from Convex storage URL
  3. Fetch hairstyle reference image bytes from CDN
  4. Rasterize the stored SVG hair mask
  5. Attempt OpenAI generation (primary, timeout-bounded)
  6. On failure → fallback to Gemini
  7. Upload result PNG to Convex storage
  8. Update job record → completed | failed

This module has NO FastAPI dependencies so it can be tested in isolation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import openai

from chevstyle_backend.config import settings
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.vision.mask_rasterization import rasterize_hair_mask
from chevstyle_backend.vision.generation.openai_generator import generate_with_openai
from chevstyle_backend.vision.generation.gemini_generator import generate_with_gemini

logger = logging.getLogger("chevstyle_backend.services.generation")

# OpenAI errors that trigger an automatic Gemini fallback
_OPENAI_FALLBACK_ERRORS = (
    openai.RateLimitError,
    openai.APIStatusError,
    openai.APITimeoutError,
    openai.BadRequestError,
)


def _fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """Download raw bytes from a public URL."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.content


async def run_generation_job(
    job_id: str,
    user_id: str,
    source_image_record: dict,
    hairstyle_record: dict,
    convex: ConvexClient,
) -> None:
    """
    Execute a full generation job asynchronously.

    Parameters
    ----------
    job_id              : Convex generation_jobs document ID.
    user_id             : Convex user ID (for ownership checks).
    source_image_record : The uploaded_images record for the user portrait.
    hairstyle_record    : The hairstyles catalog record.
    convex              : ConvexClient instance.
    """
    logger.info(f"[GenerationService] Starting job_id='{job_id}' user_id='{user_id}'")

    # ── 1. Mark job as processing ──────────────────────────────────────────
    convex.update_generation_job(
        job_id=job_id,
        status="processing",
        attempt_count=1,
    )

    portrait_bytes: bytes | None = None
    hairstyle_bytes: bytes | None = None
    mask_bytes: bytes | None = None
    result_bytes: bytes | None = None
    model_used: str | None = None
    error_message: str | None = None

    try:
        # ── 2. Fetch portrait bytes ────────────────────────────────────────
        portrait_url = source_image_record.get("url", "")
        logger.info(f"[GenerationService] Fetching portrait from: {portrait_url}")
        portrait_bytes = _fetch_bytes(portrait_url)

        # ── 3. Fetch hairstyle reference image bytes ───────────────────────
        hairstyle_url = hairstyle_record.get("imageUrl", "")
        if hairstyle_url:
            try:
                logger.info(f"[GenerationService] Fetching hairstyle ref from: {hairstyle_url}")
                hairstyle_bytes = _fetch_bytes(hairstyle_url)
            except Exception as exc:
                logger.warning(
                    f"[GenerationService] Could not fetch hairstyle image ({exc}); "
                    "falling back to text-only prompt."
                )
                hairstyle_bytes = None

        # ── 4. Rasterize hair mask ─────────────────────────────────────────
        svg_path = source_image_record.get("hair_segmentation_path")
        image_meta = source_image_record.get("image_metadata", {})
        img_w = int(image_meta.get("processed_width", 1024))
        img_h = int(image_meta.get("processed_height", 1024))

        if svg_path:
            hair_bbox = source_image_record.get("hair_bounding_box")
            logger.info(f"[GenerationService] Rasterizing hair mask {img_w}x{img_h}px")
            mask_bytes = rasterize_hair_mask(
                svg_path=svg_path,
                width=img_w,
                height=img_h,
                face_bbox=hair_bbox,
            )
        else:
            logger.warning(
                "[GenerationService] No SVG path found in source image record; "
                "proceeding without explicit mask."
            )

        hairstyle_description = hairstyle_record.get("description", "")
        hairstyle_stylist_specs = hairstyle_record.get("stylistSpecs", "")

        # ── 5. Primary: OpenAI generation ─────────────────────────────────
        openai_failed = False
        if mask_bytes is None:
            # Cannot use OpenAI images.edit without a mask — skip to Gemini
            logger.info("[GenerationService] No mask available — skipping OpenAI, using Gemini directly.")
            openai_failed = True
        else:
            try:
                logger.info("[GenerationService] Trying OpenAI generation (primary)…")
                result_bytes = generate_with_openai(
                    portrait_bytes=portrait_bytes,
                    mask_bytes=mask_bytes,
                    hairstyle_image_bytes=hairstyle_bytes,
                    hairstyle_description=hairstyle_description,
                    hairstyle_stylist_specs=hairstyle_stylist_specs,
                    timeout=settings.openai_generation_timeout_seconds,
                )
                model_used = "openai"
                logger.info("[GenerationService] OpenAI generation succeeded.")
            except _OPENAI_FALLBACK_ERRORS as exc:
                logger.warning(
                    f"[GenerationService] OpenAI failed ({type(exc).__name__}: {exc}) — "
                    "triggering Gemini fallback."
                )
                openai_failed = True

        # ── 6. Fallback: Gemini generation ────────────────────────────────
        if openai_failed:
            logger.info("[GenerationService] Trying Gemini fallback…")
            result_bytes = generate_with_gemini(
                portrait_bytes=portrait_bytes,
                hairstyle_image_bytes=hairstyle_bytes,
                hairstyle_description=hairstyle_description,
                hairstyle_stylist_specs=hairstyle_stylist_specs,
            )
            model_used = "gemini"
            logger.info("[GenerationService] Gemini fallback succeeded.")

        # ── 7. Upload result to Convex storage ─────────────────────────────
        logger.info("[GenerationService] Uploading result image to Convex storage…")
        result_storage_id = convex.store_image(result_bytes, mime_type="image/png")
        result_url = convex.get_storage_url(result_storage_id)
        logger.info(
            f"[GenerationService] Result stored: storage_id='{result_storage_id}' url='{result_url}'"
        )

        # ── 8a. Mark job as completed ──────────────────────────────────────
        convex.update_generation_job(
            job_id=job_id,
            status="completed",
            model_used=model_used,
            result_storage_id=result_storage_id,
            result_url=result_url,
        )
        logger.info(
            f"[GenerationService] Job completed: job_id='{job_id}' model='{model_used}'"
        )

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc)}"
        logger.exception(
            f"[GenerationService] Job failed: job_id='{job_id}' error='{error_message}'"
        )
        # ── 8b. Mark job as failed ─────────────────────────────────────────
        try:
            convex.update_generation_job(
                job_id=job_id,
                status="failed",
                error_message=error_message,
            )
        except Exception as update_exc:
            logger.error(
                f"[GenerationService] Could not update job to failed state: {update_exc}"
            )
