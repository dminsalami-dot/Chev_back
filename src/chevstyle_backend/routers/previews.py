"""
routers/previews.py
-------------------
Thin FastAPI router for the AI hairstyle generation (previews) API.

Endpoints:
  POST /api/v1/previews/generate   → 202 enqueue job
  GET  /api/v1/previews            → list all user jobs
  GET  /api/v1/previews/{id}       → poll job status
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from chevstyle_backend.auth.models import ClerkUser
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.dependencies import get_current_user
from chevstyle_backend.schemas.generation import (
    GeneratePreviewRequest,
    GeneratePreviewResponse,
    PreviewListResponse,
    PreviewStatusResponse,
)
from chevstyle_backend.services.generation_service import run_generation_job

logger = logging.getLogger("chevstyle_backend.routers.previews")
router = APIRouter(prefix="/api/v1/previews", tags=["Previews"])


def _job_to_status_response(job: dict, hairstyle_name: str = "") -> PreviewStatusResponse:
    """Map a raw Convex generation_jobs record to the API response model."""
    return PreviewStatusResponse(
        preview_id=str(job.get("_id") or job.get("id", "")),
        status=job.get("status", "unknown"),
        hairstyle_id=job.get("hairstyle_id", ""),
        hairstyle_name=hairstyle_name,
        image_id=job.get("source_image_id", ""),
        result_url=job.get("result_url"),
        model_used=job.get("model_used"),
        error_message=job.get("error_message"),
        attempt_count=job.get("attempt_count", 0),
        created_at=job.get("created_at", ""),
        updated_at=job.get("updated_at", ""),
    )


@router.post(
    "/generate",
    response_model=GeneratePreviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_preview(
    body: GeneratePreviewRequest,
    background_tasks: BackgroundTasks,
    user: ClerkUser = Depends(get_current_user),
):
    """
    Enqueue a hairstyle swap generation job.

    Validates:
    - image_id belongs to the requesting user and is face-verified.
    - hairstyle_id is an active catalog entry.

    Returns 202 immediately with a preview_id for polling.
    """
    convex = ConvexClient()

    # ── Validate source image ownership & face verification ───────────────
    image_record = None
    user_images = convex.list_generation_jobs(user.convex_user_id)  # reuse convex user id

    # Use the uploaded_images record — fetch via query
    # We look up the image directly by image_id, checking ownership server-side
    # (ConvexClient does not expose a get_uploaded_image yet; we inline the call)
    if not convex.is_mock:
        raw = convex.real_client.query(
            "uploaded_images:list_by_user",
            {"user_id": user.convex_user_id},
        )
        for img in raw:
            if str(img.get("_id", "")) == body.image_id:
                image_record = dict(img)
                break
    else:
        # In mock/test mode: accept any image_id, build a minimal record
        image_record = {
            "_id": body.image_id,
            "user_id": user.convex_user_id,
            "url": f"https://mock.cdn.convex.dev/img/{body.image_id}.jpg",
            "face_verified": True,
            "hair_segmentation_path": None,
            "hair_bounding_box": None,
            "image_metadata": {
                "processed_width": 1024,
                "processed_height": 1024,
            },
        }

    if not image_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IMAGE_NOT_FOUND",
        )

    if not image_record.get("face_verified", False):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="IMAGE_NOT_FACE_VERIFIED",
        )

    if image_record.get("is_deleted", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IMAGE_DELETED",
        )

    # ── Validate hairstyle exists ─────────────────────────────────────────
    hairstyle_record = convex.get_hairstyle_by_id(body.hairstyle_id)
    if not hairstyle_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HAIRSTYLE_NOT_FOUND",
        )

    hairstyle_name = hairstyle_record.get("name", "")

    # ── Create generation job (queued) ────────────────────────────────────
    job_result = convex.create_generation_job(
        user_id=user.convex_user_id,
        source_image_id=body.image_id,
        hairstyle_id=body.hairstyle_id,
    )
    job_id = str(job_result.get("id", ""))
    created_at = (job_result.get("record") or {}).get("created_at", "")

    logger.info(
        f"[PreviewsRouter] Job created: job_id='{job_id}' "
        f"user='{user.convex_user_id}' image='{body.image_id}' hairstyle='{body.hairstyle_id}'"
    )

    # ── Enqueue background task ───────────────────────────────────────────
    background_tasks.add_task(
        run_generation_job,
        job_id=job_id,
        user_id=user.convex_user_id,
        source_image_record=image_record,
        hairstyle_record=hairstyle_record,
        convex=convex,
    )

    return GeneratePreviewResponse(
        preview_id=job_id,
        status="queued",
        hairstyle_id=body.hairstyle_id,
        hairstyle_name=hairstyle_name,
        image_id=body.image_id,
        created_at=created_at,
    )


@router.get(
    "/{preview_id}",
    response_model=PreviewStatusResponse,
)
async def get_preview_status(
    preview_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    """Poll the status and result of a generation job."""
    convex = ConvexClient()
    job = convex.get_generation_job(preview_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PREVIEW_NOT_FOUND",
        )

    # Enforce ownership
    if job.get("user_id") != user.convex_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FORBIDDEN",
        )

    # Resolve hairstyle name if possible
    hairstyle_name = ""
    hairstyle = convex.get_hairstyle_by_id(job.get("hairstyle_id", ""))
    if hairstyle:
        hairstyle_name = hairstyle.get("name", "")

    return _job_to_status_response(job, hairstyle_name)


@router.get(
    "",
    response_model=PreviewListResponse,
)
async def list_previews(
    user: ClerkUser = Depends(get_current_user),
):
    """List all generation jobs for the authenticated user."""
    convex = ConvexClient()
    jobs = convex.list_generation_jobs(user.convex_user_id)

    responses: list[PreviewStatusResponse] = []
    for job in jobs:
        hairstyle_name = ""
        hairstyle = convex.get_hairstyle_by_id(job.get("hairstyle_id", ""))
        if hairstyle:
            hairstyle_name = hairstyle.get("name", "")
        responses.append(_job_to_status_response(job, hairstyle_name))

    return PreviewListResponse(previews=responses, total=len(responses))
