"""
mask_rasterization.py
---------------------
Converts a Moondream SVG path string to a rasterized RGBA PNG mask
suitable for the OpenAI images.edit endpoint.

The returned PNG has:
  - Hair region: alpha = 0   (transparent → OpenAI paints here)
  - Non-hair:    alpha = 255 (opaque → OpenAI preserves)

Processing steps:
  1. Wrap the bare path string in a minimal SVG document.
  2. Rasterize to PNG bytes via cairosvg.
  3. Convert to 1-channel binary mask via Pillow.
  4. Dilate 3 px + feather 2 px (Gaussian blur) for edge blending.
  5. (Optional) Zero-out the face bounding box so we never paint over the face.
  6. Invert and embed in RGBA PNG for OpenAI format.
"""

from __future__ import annotations

import io
import logging

import cairosvg
import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger("chevstyle_backend.vision.mask_rasterization")


def rasterize_hair_mask(
    svg_path: str,
    width: int,
    height: int,
    face_bbox: dict | None = None,
) -> bytes:
    """
    Convert a Moondream normalised SVG path string into a rasterised RGBA
    PNG mask for OpenAI image editing.

    Parameters
    ----------
    svg_path : str
        Bare SVG path data string (starts with "M", "m", etc.).
        Moondream returns coordinates normalised to [0, 1], so we wrap
        the path in an SVG viewBox="0 0 1 1" and scale to (width, height).
    width : int
        Target pixel width (portrait image width).
    height : int
        Target pixel height (portrait image height).
    face_bbox : dict | None
        Optional face bounding box in normalised [0,1] coords:
        {"x_min": float, "y_min": float, "x_max": float, "y_max": float}
        If provided, the face region is excluded from the hair mask.

    Returns
    -------
    bytes
        RGBA PNG bytes where the hair region is alpha=0 (transparent).
    """
    # 1. Wrap in a minimal SVG document (viewBox 0 0 1 1 for normalised coords)
    svg_doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 1 1" width="{width}" height="{height}">'
        f'<path d="{svg_path}" fill="white" />'
        f"</svg>"
    )

    # 2. Rasterize SVG → PNG bytes
    png_bytes = cairosvg.svg2png(bytestring=svg_doc.encode())

    # 3. Open as PIL image, extract luminance as 1-channel mask
    svg_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    # White pixels = hair region → we want those as 1 (mask=True)
    r, g, b, a = svg_img.split()
    # Use red channel as mask proxy (white = 255, black = 0)
    mask_arr = np.array(r, dtype=np.uint8)

    # Threshold to binary
    binary = (mask_arr > 127).astype(np.uint8) * 255

    # 4. Dilate 3 px then blur 2 px for edge feathering
    pil_mask = Image.fromarray(binary, mode="L")
    pil_mask = pil_mask.filter(ImageFilter.MaxFilter(size=7))   # ~3px dilation
    pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=2))

    # 5. Zero out face bounding box (protect face from being painted)
    if face_bbox:
        mask_np = np.array(pil_mask, dtype=np.uint8)
        x0 = int(face_bbox.get("x_min", 0) * width)
        y0 = int(face_bbox.get("y_min", 0) * height)
        x1 = int(face_bbox.get("x_max", 1) * width)
        y1 = int(face_bbox.get("y_max", 1) * height)
        # Clamp to image bounds
        x0 = max(0, min(x0, width - 1))
        y0 = max(0, min(y0, height - 1))
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))
        mask_np[y0:y1, x0:x1] = 0
        pil_mask = Image.fromarray(mask_np, mode="L")

    # 6. Build RGBA PNG:
    #    - Hair region (mask=255) → alpha=0 (transparent → OpenAI paints here)
    #    - Background (mask=0)    → alpha=255 (opaque → OpenAI preserves)
    mask_np_final = np.array(pil_mask, dtype=np.uint8)
    alpha_channel = 255 - mask_np_final  # invert: hair=0, bg=255

    rgba = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rgba.putalpha(Image.fromarray(alpha_channel, mode="L"))

    buf = io.BytesIO()
    rgba.save(buf, format="PNG")
    result_bytes = buf.getvalue()

    logger.debug(
        f"[MaskRasterization] mask generated: {width}x{height}px | "
        f"hair_px={int(mask_np_final.astype(bool).sum())} | "
        f"face_bbox={face_bbox}"
    )
    return result_bytes
