"""Pydantic schemas for the AI hairstyle generation (previews) API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class GeneratePreviewRequest(BaseModel):
    """Request body for POST /api/v1/previews/generate."""
    image_id: str
    hairstyle_id: str


class GeneratePreviewResponse(BaseModel):
    """Immediate 202 response returned when a job is enqueued."""
    preview_id: str
    status: str
    hairstyle_id: str
    hairstyle_name: str
    image_id: str
    created_at: str


class PreviewStatusResponse(BaseModel):
    """Full job status returned by GET /api/v1/previews/{preview_id}."""
    preview_id: str
    status: str
    hairstyle_id: str
    hairstyle_name: str
    image_id: str
    result_url: Optional[str] = None
    model_used: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int = 0
    created_at: str
    updated_at: str


class PreviewListResponse(BaseModel):
    """Response for GET /api/v1/previews."""
    previews: list[PreviewStatusResponse]
    total: int
