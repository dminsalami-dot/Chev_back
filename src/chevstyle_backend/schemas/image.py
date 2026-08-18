from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class BoundingBox(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class HairSegmentationResult(BaseModel):
    path: str
    bbox: BoundingBox


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
    hair_segmentation_path: Optional[str] = None
    image_metadata: ImageMetadata
    created_at: datetime
