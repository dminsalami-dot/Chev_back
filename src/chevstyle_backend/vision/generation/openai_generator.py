"""
openai_generator.py
-------------------
Primary AI image generation engine using OpenAI gpt-image-2.

Uses the images.edit endpoint with:
  - base image  : user portrait (JPEG/PNG bytes)
  - mask        : RGBA PNG where transparent = hair region to paint
  - prompt      : hairstyle instruction (+ embedded reference description
                  when multi-image is unavailable)

Raises on any failure so the caller can trigger the Gemini fallback.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Callable

import httpx
import openai

from chevstyle_backend.config import settings

logger = logging.getLogger("chevstyle_backend.vision.generation.openai")

_EDIT_PROMPT = (
    "Precise photo editing task: Replace ONLY the hairstyle of the person "
    "in the base image with the exact hairstyle, texture, volume, and color "
    "shown in the reference hairstyle image. "
    "Keep the person's face, facial features, skin tone, lighting, head angle, "
    "expression, and background COMPLETELY UNCHANGED. "
    "Ensure the hairline attaches naturally and seamlessly to their scalp and forehead."
)

_EDIT_PROMPT_TEXT_ONLY = (
    "Precise photo editing task: Replace ONLY the hairstyle of the person "
    "in the base image with this hairstyle — {description}. "
    "Stylist specifications: {stylist_specs}. "
    "Keep the person's face, facial features, skin tone, lighting, head angle, "
    "expression, and background COMPLETELY UNCHANGED. "
    "Ensure the hairline attaches naturally and seamlessly to their scalp and forehead."
)


def generate_with_openai(
    portrait_bytes: bytes,
    mask_bytes: bytes,
    hairstyle_image_bytes: bytes | None,
    hairstyle_description: str = "",
    hairstyle_stylist_specs: str = "",
    timeout: int | None = None,
) -> bytes:
    """
    Edit the portrait using OpenAI gpt-image-2 image editing.

    Parameters
    ----------
    portrait_bytes       : JPEG/PNG portrait image bytes.
    mask_bytes           : RGBA PNG mask (transparent = paint zone).
    hairstyle_image_bytes: Reference hairstyle image bytes (or None for text-only).
    hairstyle_description: Hairstyle catalog description (fallback prompt).
    hairstyle_stylist_specs: Stylist specs from catalog (fallback prompt).
    timeout              : Request timeout in seconds.

    Returns
    -------
    bytes : PNG bytes of the edited portrait.

    Raises
    ------
    openai.RateLimitError, openai.APIStatusError, openai.APITimeoutError,
    openai.BadRequestError — all re-raised so the caller can fall back.
    """
    _timeout = timeout or settings.openai_generation_timeout_seconds

    client = openai.OpenAI(
        api_key=settings.openai_api_key,
        timeout=float(_timeout),
    )

    portrait_file = io.BytesIO(portrait_bytes)
    portrait_file.name = "portrait.png"

    mask_file = io.BytesIO(mask_bytes)
    mask_file.name = "mask.png"

    if hairstyle_image_bytes:
        hairstyle_file = io.BytesIO(hairstyle_image_bytes)
        hairstyle_file.name = "hairstyle.png"
        image_input = [portrait_file, hairstyle_file]
        prompt = _EDIT_PROMPT
        logger.info("[OpenAIGenerator] Using multi-image edit mode with reference hairstyle.")
    else:
        image_input = portrait_file
        prompt = _EDIT_PROMPT_TEXT_ONLY.format(
            description=hairstyle_description,
            stylist_specs=hairstyle_stylist_specs,
        )
        logger.info("[OpenAIGenerator] Using text-only prompt (no reference image).")

    logger.info(f"[OpenAIGenerator] Calling images.edit | timeout={_timeout}s")

    response = client.images.edit(
        model="gpt-image-1",
        image=image_input,
        mask=mask_file,
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    item = response.data[0]
    if getattr(item, "b64_json", None):
        result_bytes = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        logger.info(f"[OpenAIGenerator] Downloading result from URL: {item.url}")
        resp = httpx.get(item.url, timeout=30.0)
        resp.raise_for_status()
        result_bytes = resp.content
    else:
        raise ValueError("[OpenAIGenerator] OpenAI returned neither b64_json nor url.")

    logger.info(
        f"[OpenAIGenerator] Success — result image size: {len(result_bytes)} bytes"
    )
    return result_bytes
