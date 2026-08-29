"""
gemini_generator.py
-------------------
Fallback AI image generation engine using Google Gemini
(gemini-2.0-flash-preview-image-generation).

Called when OpenAI fails due to rate limits, server errors,
content moderation blocks, or timeouts.

Input parts:
  1. Text prompt
  2. User portrait image bytes (inline_data)
  3. Target hairstyle reference image bytes (inline_data, if available)

Returns PNG bytes of the generated portrait.
Raises on any failure.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from chevstyle_backend.config import settings

logger = logging.getLogger("chevstyle_backend.vision.generation.gemini")

_PROMPT = (
    "You are an expert realistic portrait retoucher. "
    "Using Image 1 as the primary portrait and Image 2 as the hairstyle reference: "
    "Generate a photorealistic portrait of the person in Image 1 having their "
    "hairstyle replaced with the hairstyle shown in Image 2. "
    "Preserve the exact facial identity, eye gaze direction, skin tone, "
    "clothing, lighting conditions, and background of Image 1 with zero alterations. "
    "Output only the edited portrait image."
)

_PROMPT_TEXT_ONLY = (
    "You are an expert realistic portrait retoucher. "
    "Precisely edit the hairstyle in Image 1 to match this description: {description}. "
    "Stylist specifications: {stylist_specs}. "
    "Preserve the exact facial identity, eye gaze direction, skin tone, "
    "clothing, lighting conditions, and background with zero alterations. "
    "Output only the edited portrait image."
)


def generate_with_gemini(
    portrait_bytes: bytes,
    hairstyle_image_bytes: bytes | None,
    hairstyle_description: str = "",
    hairstyle_stylist_specs: str = "",
) -> bytes:
    """
    Generate a hairstyle-swapped portrait using Gemini image generation.

    Parameters
    ----------
    portrait_bytes        : JPEG/PNG user portrait bytes.
    hairstyle_image_bytes : Reference hairstyle image bytes (or None).
    hairstyle_description : Catalog description (used in text-only prompt fallback).
    hairstyle_stylist_specs: Catalog stylist specs.

    Returns
    -------
    bytes : PNG bytes of the edited portrait.

    Raises
    ------
    Any google.genai exception — re-raised to caller.
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    if hairstyle_image_bytes:
        prompt_text = _PROMPT
        logger.info("[GeminiGenerator] Using multi-image generation with reference.")
    else:
        prompt_text = _PROMPT_TEXT_ONLY.format(
            description=hairstyle_description,
            stylist_specs=hairstyle_stylist_specs,
        )
        logger.info("[GeminiGenerator] Using text-only prompt (no reference image).")

    # Build content parts
    parts: list[types.Part] = [
        types.Part(text=prompt_text),
        types.Part(
            inline_data=types.Blob(
                mime_type="image/jpeg",
                data=portrait_bytes,
            )
        ),
    ]

    if hairstyle_image_bytes:
        parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type="image/jpeg",
                    data=hairstyle_image_bytes,
                )
            )
        )

    logger.info("[GeminiGenerator] Calling gemini-2.0-flash-preview-image-generation")

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=parts,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    # Extract the first image part from the response
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                result_bytes = bytes(part.inline_data.data)
                logger.info(
                    f"[GeminiGenerator] Success — result size: {len(result_bytes)} bytes"
                )
                return result_bytes

    raise ValueError(
        "[GeminiGenerator] Gemini returned no image data in the response."
    )
