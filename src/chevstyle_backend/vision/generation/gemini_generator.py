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

_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"

_PROMPT = (
    "Virtual Hairstyle Try-On Task:\n\n"
    "You are given two images:\n"
    "- Image 1: The user's portrait (Base Subject).\n"
    "- Image 2: Reference photo for the hairstyle '{name}'.\n\n"
    "YOUR TASK:\n"
    "Generate a photorealistic portrait of the EXACT SAME PERSON from Image 1, "
    "having their hairstyle replaced with the haircut/hairstyle shown in Image 2.\n"
    "{details}"
    "\nSTRICT REQUIREMENTS:\n"
    "1. SUBJECT IDENTITY (IMAGE 1 ONLY):\n"
    "   - The person in the output MUST be the person from Image 1.\n"
    "   - You MUST keep their exact facial features, facial structure, eyes, nose, mouth, "
    "skin tone, age, gender, facial hair, expression, head posture, clothing, lighting, "
    "and background 100% UNCHANGED from Image 1.\n"
    "2. HAIRSTYLE (IMAGE 2 ONLY):\n"
    "   - Replace ONLY the hair on the subject's head with the haircut, texture, curl pattern, "
    "length, fade/taper, volume, and color shown in Image 2.\n"
    "   - Seamlessly blend the new hairstyle into the subject's scalp and natural hairline.\n"
    "3. DO NOT USE THE FACE OR IDENTITY FROM IMAGE 2:\n"
    "   - Image 2 is STRICTLY a reference for the hair cut and style. DO NOT render the person, "
    "face, or background from Image 2.\n\n"
    "Output ONLY the final edited portrait."
)

_PROMPT_TEXT_ONLY = (
    "Virtual Hairstyle Try-On Task:\n\n"
    "You are given Image 1 which is the user's portrait.\n\n"
    "YOUR TASK:\n"
    "Generate a photorealistic portrait of the EXACT SAME PERSON from Image 1, "
    "having their hairstyle changed to '{name}'.\n"
    "{details}"
    "\nSTRICT REQUIREMENTS:\n"
    "1. SUBJECT IDENTITY:\n"
    "   - The person in the output MUST be the person from Image 1.\n"
    "   - You MUST keep their exact facial features, facial structure, eyes, nose, mouth, "
    "skin tone, age, gender, facial hair, expression, head posture, clothing, lighting, "
    "and background 100% UNCHANGED from Image 1.\n"
    "2. HAIRSTYLE:\n"
    "   - Apply the specified hairstyle naturally to the subject's head and hairline.\n\n"
    "Output ONLY the final edited portrait."
)


def generate_with_gemini(
    portrait_bytes: bytes,
    hairstyle_image_bytes: bytes | None,
    hairstyle_name: str = "",
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

    details_text = ""
    if hairstyle_description:
        details_text += f"- Style description: {hairstyle_description}\n"
    if hairstyle_stylist_specs:
        details_text += f"- Stylist specs: {hairstyle_stylist_specs}\n"

    if hairstyle_image_bytes:
        prompt_text = _PROMPT.format(
            name=hairstyle_name or "Target Hairstyle",
            details=details_text,
        )
        logger.info("[GeminiGenerator] Using multi-image generation with reference.")
    else:
        prompt_text = _PROMPT_TEXT_ONLY.format(
            name=hairstyle_name or "Target Hairstyle",
            details=details_text,
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

    logger.info(f"[GeminiGenerator] Calling {_GEMINI_IMAGE_MODEL}")

    response = client.models.generate_content(
        model=_GEMINI_IMAGE_MODEL,
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
