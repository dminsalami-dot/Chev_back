from unittest.mock import MagicMock, patch
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from chevstyle_backend.app import app
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.schemas.image import BoundingBox, HairSegmentationResult

client = TestClient(app)


def _create_dummy_image_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_convex_client_mock_stores_hair_segmentation_path():
    convex = ConvexClient()
    record = convex.create_uploaded_image_record(
        user_id="user_123",
        storage_id="storage_123",
        url="https://example.com/img.jpg",
        face_verified=True,
        face_verification_score=0.99,
        hair_bounding_box={"x_min": 0.1, "y_min": 0.2, "x_max": 0.6, "y_max": 0.8},
        hair_segmentation_confidence=None,
        hair_segmentation_path="M.986,.982C.983,.972",
        image_metadata={"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "format": "JPEG"},
        consent_given=True,
        image_validated=True,
    )

    assert record["hair_segmentation_path"] == "M.986,.982C.983,.972"
    assert record["user_id"] == "user_123"
    assert record["face_verified"] is True
    assert record["hair_bounding_box"] == {"x_min": 0.1, "y_min": 0.2, "x_max": 0.6, "y_max": 0.8}


def test_convex_client_real_passes_hair_segmentation_path():
    mock_real_instance = MagicMock()
    mock_real_instance.mutation.return_value = {
        "id": "img_doc_123",
        "record": {
            "user_id": "user_123",
            "hair_segmentation_path": "M.986,.982C.983,.972",
        },
    }

    convex = ConvexClient()
    convex.is_mock = False
    convex.real_client = mock_real_instance

    record = convex.create_uploaded_image_record(
        user_id="user_123",
        storage_id="storage_123",
        url="https://example.com/img.jpg",
        face_verified=True,
        face_verification_score=None,
        hair_bounding_box={"x_min": 0.1, "y_min": 0.2, "x_max": 0.6, "y_max": 0.8},
        hair_segmentation_confidence=None,
        hair_segmentation_path="M.986,.982C.983,.972",
        image_metadata={"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "format": "JPEG"},
    )

    mock_real_instance.mutation.assert_called_once()
    call_args = mock_real_instance.mutation.call_args
    assert call_args[0][0] == "uploaded_images:create"
    assert call_args[0][1]["hair_segmentation_path"] == "M.986,.982C.983,.972"
    assert record["hair_segmentation_path"] == "M.986,.982C.983,.972"


@patch("chevstyle_backend.routers.images.validate_image", return_value=True)
@patch("chevstyle_backend.routers.images.verify_face", return_value=(True, "Exactly one human face is clearly visible."))
@patch("chevstyle_backend.routers.images.segment_hair")
@patch("chevstyle_backend.routers.images.ConvexClient")
def test_upload_image_passes_hair_segmentation_path(
    mock_convex_cls,
    mock_segment_hair,
    mock_verify_face,
    mock_validate_image,
):
    mock_segment_hair.return_value = HairSegmentationResult(
        bbox=BoundingBox(x_min=0.1, y_min=0.2, x_max=0.6, y_max=0.8),
        path="M.986,.982C.983,.972",
    )
    mock_convex_inst = MagicMock()
    mock_convex_cls.return_value = mock_convex_inst
    mock_convex_inst.store_image.return_value = "storage_123"
    mock_convex_inst.get_storage_url.return_value = "https://cdn.example.com/img.jpg"
    mock_convex_inst.create_uploaded_image_record.return_value = {
        "image_id": "img_123",
        "created_at": "2026-08-29T20:00:00Z",
    }

    img_bytes = _create_dummy_image_bytes()
    headers = {"Authorization": "Bearer test-token"}
    response = client.post(
        "/api/v1/images/upload",
        files={"file": ("portrait.jpg", img_bytes, "image/jpeg")},
        data={"consent_given": "true"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["hair_segmentation_path"] == "M.986,.982C.983,.972"
    assert body["hair_bounding_box"] == {"x_min": 0.1, "y_min": 0.2, "x_max": 0.6, "y_max": 0.8}

    mock_convex_inst.create_uploaded_image_record.assert_called_once()
    kwargs = mock_convex_inst.create_uploaded_image_record.call_args.kwargs
    assert kwargs["hair_segmentation_path"] == "M.986,.982C.983,.972"
