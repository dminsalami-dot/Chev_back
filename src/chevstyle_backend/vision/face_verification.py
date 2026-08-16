
import base64
import json
from google import genai
from chevstyle_backend.config import settings


PROMPT = """You are an image validation system for a hairstyle virtual try-on application.

Analyze the provided image and determine whether it contains **exactly one visible human face**.

### Validation Rules

Return `true` ONLY when:

* The image contains exactly **one** human face.
* The face belongs to a real human.
* The face is sufficiently visible to identify it as a human face.

Return `false` when:

* There are **zero human faces**.
* There are **two or more human faces**.
* The image contains only part of a face that is too obscured to confidently identify.
* The image contains a cartoon, drawing, painting, sculpture, mannequin, doll, or other non-human representation of a face.
* The image is otherwise unsuitable for a hairstyle virtual try-on.

### Required Response

Return ONLY valid JSON in exactly this format:

{
  "valid": true,
  "message": "Exactly one human face is clearly visible."
}

The `valid` field must be a boolean: `true` or `false`.

The `message` must be exactly **one concise sentence** explaining why the image was accepted or rejected.

Do not include any additional fields, markdown, or commentary.

### Examples

One human face:
{
  "valid": true,
  "message": "Exactly one human face is clearly visible."
}

No face:
{
  "valid": false,
  "message": "No human face is visible in the image."
}

Multiple faces:
{
  "valid": false,
  "message": "The image contains more than one human face."
}

Non-human face:
{
  "valid": false,
  "message": "The image contains a non-human representation rather than a real human face."
}"""



def verify_face(image_bytes: bytes) -> tuple[bool, str]:
    """
    Sends the image to Gemini and determines whether it contains exactly one
    real human face suitable for a hairstyle virtual try-on.

    Returns:
        (is_human: bool, message: str)

    Never raises — returns (False, error_message) on any unexpected failure.
    """
    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=[
                {
                    "type": "image",
                    "data": image_b64,
                    "mime_type": "image/jpeg",
                },
                {
                    "type": "text",
                    "text": PROMPT,
                },
            ],
        )

        content = interaction.output_text.strip()

        # Strip optional markdown code fences
        if content.startswith("```json"):
            content = content[7:].rstrip("`").strip()
        elif content.startswith("```"):
            content = content[3:].rstrip("`").strip()

        result = json.loads(content)

        is_human: bool = bool(result.get("valid", False))
        message: str = result.get(
            "message",
            "No message returned."
        )

        print(
            f"[Face Verification] is_human={is_human} | message='{message}'"
        )

        return is_human, message

    except Exception as exc:
        error_msg = f"Gemini face verification failed: {str(exc)}"
        print(f"[Face Verification] ERROR | {error_msg}")
        return False, error_msg