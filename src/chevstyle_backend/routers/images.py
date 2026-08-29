import io
import logging
import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from PIL import Image

from chevstyle_backend.dependencies import get_current_user
from chevstyle_backend.auth.models import ClerkUser
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.vision.image_validation import validate_image
from chevstyle_backend.vision.face_verification import verify_face
from chevstyle_backend.vision.hair_segmentation import segment_hair
from chevstyle_backend.schemas.image import ImageMetadata, UploadedImageResponse

logger = logging.getLogger("chevstyle_backend.routers.images")
router = APIRouter(prefix="/api/v1/images", tags=["Images"])


def _save_temp(file_bytes: bytes, suffix: str = ".jpg") -> str:
    """Write bytes to a named temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(file_bytes)
    finally:
        tmp.close()
    return tmp.name


def _extract_metadata(file_bytes: bytes) -> ImageMetadata:
    """Extract basic image metadata using PIL (no processing, just read)."""
    img = Image.open(io.BytesIO(file_bytes))
    width, height = img.size
    fmt = img.format or "JPEG"
    return ImageMetadata(
        original_width=width,
        original_height=height,
        processed_width=width,
        processed_height=height,
        format=fmt,
    )


@router.post("/upload", response_model=UploadedImageResponse, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    consent_given: bool = Form(...),
    user: ClerkUser = Depends(get_current_user),
):
    logger.info(
        f"Image upload requested by user='{user.convex_user_id}' "
        f"with consent_given={consent_given}"
    )

    if not consent_given:
        logger.warning(
            f"Upload rejected: Consent required for user='{user.convex_user_id}'"
        )
        raise HTTPException(status_code=400, detail="CONSENT_REQUIRED")

    file_bytes = await file.read()
    logger.info(f"Read {len(file_bytes)} bytes from uploaded file '{file.filename}'")

    # 1. Image Validation (image_validation.py layer)
    tmp_path: str | None = None
    try:
        tmp_path = _save_temp(file_bytes, suffix=".jpg")
        image_validated: bool = validate_image(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    print(
        f"[Image Validation] image_validated={image_validated} "
        f"| user_id='{user.convex_user_id}' | file='{file.filename}'"
    )

    if not image_validated:
        raise HTTPException(status_code=422, detail="IMAGE_VALIDATION_FAILED")

    # 2. Extract metadata from raw bytes (PIL read-only, no processing)
    try:
        metadata = _extract_metadata(file_bytes)
        logger.info(
            f"Image metadata: {metadata.original_width}x{metadata.original_height}, "
            f"format='{metadata.format}'"
        )
    except Exception as exc:
        logger.error(f"Metadata extraction failed: {str(exc)}")
        raise HTTPException(status_code=415, detail="UNSUPPORTED_FORMAT")

    # 3. Face Verification (Gemini — is_human check only)
    is_human, face_message = verify_face(file_bytes)
    logger.info(f"Face verification: is_human={is_human} | message='{face_message}'")
    print(
        f"[Face Verification] is_human={is_human} | message='{face_message}' "
        f"| user_id='{user.convex_user_id}' | file='{file.filename}'"
    )

    if not is_human:
        raise HTTPException(status_code=422, detail=face_message)

    # 4. Hair Segmentation
    try:
        segmentation_result = segment_hair(file_bytes)
        logger.info(
            f"Hair segmentation: "
            f"bounding_box={segmentation_result.bbox.model_dump()}"
        )
    except Exception as exc:
        logger.error(f"Hair segmentation failed: {str(exc)}")
        raise exc

    # 5. Upload to Convex Storage
    try:
        convex = ConvexClient()
        storage_id = convex.store_image(file_bytes, mime_type=file.content_type or "image/jpeg")
        url = convex.get_storage_url(storage_id)
        logger.info(
            f"Uploaded image to Convex Storage: "
            f"storage_id='{storage_id}', url='{url}'"
        )
    except Exception as exc:
        logger.error(f"Convex Storage upload failed: {str(exc)}")
        raise exc

    # 6. Write Record
    try:
        record = convex.create_uploaded_image_record(
            user_id=user.convex_user_id,
            storage_id=storage_id,
            url=url,
            face_verified=is_human,
            face_verification_score=None,
            hair_bounding_box=segmentation_result.bbox.model_dump(),
            hair_segmentation_confidence=None,
            hair_segmentation_path=segmentation_result.path,
            image_metadata=metadata.model_dump(),
            consent_given=True,
            image_validated=True,
        )
        logger.info(
            f"Created image record: "
            f"image_id='{record.get('image_id') or record.get('_id') or storage_id}'"
        )
    except Exception as exc:
        logger.error(f"Convex record creation failed: {str(exc)}")
        raise exc

    # Safely resolve image_id and created_at regardless of Convex response shape
    image_id = (
        record.get("image_id")
        or record.get("_id")
        or storage_id
    )
    created_at_raw = record.get("created_at") or datetime.now(timezone.utc).isoformat()
    created_at = (
        created_at_raw
        if isinstance(created_at_raw, datetime)
        else datetime.fromisoformat(created_at_raw)
    )

    # 7. Return Response
    return UploadedImageResponse(
        image_id=str(image_id),
        url=url,
        face_verified=is_human,
        face_verification_score=None,
        hair_bounding_box=segmentation_result.bbox,
        hair_segmentation_path=segmentation_result.path,
        image_metadata=metadata,
        created_at=created_at,
    )
