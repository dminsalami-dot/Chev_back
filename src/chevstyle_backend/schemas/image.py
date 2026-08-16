from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class HairSegmentationResult(BaseModel):
    bounding_box: BoundingBox
    confidence: float
    mask_image_url: Optional[str] = None


class ImageMetadata(BaseModel):
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    format: str


class UploadedImageResponse(BaseModel):
    image_id: str
    url: str
    face_verified: bool
    face_verification_score: Optional[float] = None
    hair_bounding_box: Optional[BoundingBox] = None
    hair_segmentation_confidence: Optional[float] = None
    image_metadata: ImageMetadata
    created_at: datetime
