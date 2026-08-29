"""Tests for vision/mask_rasterization.py"""

from unittest.mock import patch, MagicMock
import io
import pytest

import numpy as np
from PIL import Image


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_png_bytes(width: int, height: int, color: str = "white") -> bytes:
    img = Image.new("RGBA", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _svg_path_square() -> str:
    """A simple normalised SVG path that forms a top-centre rectangle (hair region)."""
    return "M 0.2 0 L 0.8 0 L 0.8 0.4 L 0.2 0.4 Z"


# ── Tests ─────────────────────────────────────────────────────────────────────

@patch("chevstyle_backend.vision.mask_rasterization.cairosvg.svg2png")
def test_rasterize_returns_png_of_correct_dimensions(mock_svg2png):
    """Output PNG must match requested (width, height)."""
    from chevstyle_backend.vision.mask_rasterization import rasterize_hair_mask

    # cairosvg returns a white-on-black PNG
    mock_svg2png.return_value = _make_png_bytes(100, 100, "white")

    result = rasterize_hair_mask(
        svg_path=_svg_path_square(),
        width=100,
        height=100,
    )

    out_img = Image.open(io.BytesIO(result))
    assert out_img.size == (100, 100), f"Expected (100,100), got {out_img.size}"
    assert out_img.mode == "RGBA"


@patch("chevstyle_backend.vision.mask_rasterization.cairosvg.svg2png")
def test_rasterize_hair_region_is_transparent(mock_svg2png):
    """In the output RGBA PNG, pixels where hair=True should be alpha=0 (transparent)."""
    from chevstyle_backend.vision.mask_rasterization import rasterize_hair_mask

    # Simulate cairosvg returning a fully white PNG (entire image = hair)
    mock_svg2png.return_value = _make_png_bytes(50, 50, "white")

    result = rasterize_hair_mask(svg_path="M 0 0 L 1 0 L 1 1 L 0 1 Z", width=50, height=50)

    out_img = Image.open(io.BytesIO(result)).convert("RGBA")
    arr = np.array(out_img)
    # Alpha channel — most hair pixels should be 0 (transparent) after inversion
    alpha = arr[:, :, 3]
    transparent_ratio = (alpha == 0).sum() / alpha.size
    assert transparent_ratio > 0.5, (
        f"Expected >50% transparent pixels (hair zone), got {transparent_ratio:.2%}"
    )


@patch("chevstyle_backend.vision.mask_rasterization.cairosvg.svg2png")
def test_face_bbox_zeros_out_face_region(mock_svg2png):
    """Face bounding box area should be fully opaque (alpha=255) in the output mask."""
    from chevstyle_backend.vision.mask_rasterization import rasterize_hair_mask

    # Full-white PNG so the hair mask covers everything
    mock_svg2png.return_value = _make_png_bytes(100, 100, "white")

    face_bbox = {"x_min": 0.2, "y_min": 0.2, "x_max": 0.8, "y_max": 0.8}
    result = rasterize_hair_mask(
        svg_path="M 0 0 L 1 0 L 1 1 L 0 1 Z",
        width=100,
        height=100,
        face_bbox=face_bbox,
    )

    out_img = Image.open(io.BytesIO(result)).convert("RGBA")
    arr = np.array(out_img)

    # Face bbox in pixels
    x0, y0, x1, y1 = 20, 20, 80, 80
    face_alpha = arr[y0:y1, x0:x1, 3]

    # All face pixels should be fully opaque (alpha=255), not painted
    assert (face_alpha == 255).all(), (
        "Face region pixels should be fully opaque (alpha=255) to prevent painting over the face."
    )


@patch("chevstyle_backend.vision.mask_rasterization.cairosvg.svg2png")
def test_rasterize_with_no_face_bbox_does_not_raise(mock_svg2png):
    """rasterize_hair_mask should work fine without a face_bbox."""
    from chevstyle_backend.vision.mask_rasterization import rasterize_hair_mask

    mock_svg2png.return_value = _make_png_bytes(64, 64, "black")

    result = rasterize_hair_mask(
        svg_path=_svg_path_square(),
        width=64,
        height=64,
        face_bbox=None,
    )
    assert isinstance(result, bytes)
    assert len(result) > 0
