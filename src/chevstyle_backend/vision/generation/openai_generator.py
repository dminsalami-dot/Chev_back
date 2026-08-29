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
    "Virtual Hairstyle Try-On Editing Task:\n"
    "- Base Image (Image 1): The user's portrait. The output MUST be this EXACT same person.\n"
    "- Target Hairstyle Reference (Image 2): Hairstyle reference for '{name}'.\n\n"
    "TASK:\n"
    "Replace ONLY the hair of the person in Image 1 with the exact hairstyle, cut, texture, "
    "curl pattern, volume, taper/fade, and styling shown in Image 2.\n"
    "{details}"
    "\nCRITICAL CONSTRAINTS:\n"
    "1. IDENTITY: The face, eyes, nose, lips, facial features, bone structure, skin tone, "
    "facial hair, expression, head posture, neck, clothing, lighting, and background MUST "
    "remain 100% IDENTICAL to Image 1 (the user).\n"
    "2. DO NOT use the face, identity, head shape, or background of the person in Image 2. "
    "Image 2 is strictly a reference for the hair cut and style only.\n"
    "3. Seamlessly attach the new hairstyle to the scalp and natural hairline in Image 1."
)

_EDIT_PROMPT_TEXT_ONLY = (
    "Virtual Hairstyle Try-On Editing Task:\n"
    "- Base Image: The user's portrait. The output MUST be this EXACT same person.\n\n"
    "TASK:\n"
    "Replace ONLY the hair of the person with the hairstyle: '{name}'.\n"
    "{details}"
    "\nCRITICAL CONSTRAINTS:\n"
    "1. IDENTITY: The face, eyes, nose, lips, facial features, bone structure, skin tone, "
    "facial hair, expression, head posture, neck, clothing, lighting, and background MUST "
    "remain 100% IDENTICAL to the base portrait.\n"
    "2. Seamlessly attach the new hairstyle to the scalp and natural hairline."
)


def generate_with_openai(
    portrait_bytes: bytes,
    mask_bytes: bytes,
    hairstyle_image_bytes: bytes | None,
    hairstyle_name: str = "",
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

    details_text = ""
    if hairstyle_description:
        details_text += f"- Style description: {hairstyle_description}\n"
    if hairstyle_stylist_specs:
        details_text += f"- Stylist specs: {hairstyle_stylist_specs}\n"

    if hairstyle_image_bytes:
        hairstyle_file = io.BytesIO(hairstyle_image_bytes)
        hairstyle_file.name = "hairstyle.png"
        image_input = [portrait_file, hairstyle_file]
        prompt = _EDIT_PROMPT.format(
            name=hairstyle_name or "Target Hairstyle",
            details=details_text,
        )
        logger.info("[OpenAIGenerator] Using multi-image edit mode with reference hairstyle.")
    else:
        image_input = portrait_file
        prompt = _EDIT_PROMPT_TEXT_ONLY.format(
            name=hairstyle_name or "Target Hairstyle",
            details=details_text,
        )
        logger.info("[OpenAIGenerator] Using text-only prompt (no reference image).")

    logger.info(f"[OpenAIGenerator] Calling images.edit | timeout={_timeout}s")

    response = client.images.edit(
        model="gpt-image-2",
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
