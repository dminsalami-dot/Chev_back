import cv2
import numpy as np
import json
import base64
from google import genai
from google.genai import types
from fastapi import HTTPException
from chevstyle_backend.config import settings

CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def detect_faces_opencv(image_bytes: bytes) -> dict:
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"detected": False, "face_count": 0, "confidence": 0.0, "faces": []}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    
    return {
        "detected": len(faces) > 0,
        "face_count": len(faces),
        "confidence": 1.0 if len(faces) > 0 else 0.0,
        "faces": [{"x": int(x), "y": int(y), "width": int(w), "height": int(h)} for (x, y, w, h) in faces]
    }

def verify_face_gemini(image_bytes: bytes) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = """
You are an image analysis assistant.
Analyze the provided image and answer ONLY in JSON:

{
  "has_human_face": true,
  "face_clearly_visible": true,
  "lighting_adequate": true,
  "face_obstructed": false,
  "image_quality_score": 0.0,
  "issues": []
}

Be factual and concise. Do not add any commentary outside the JSON object.
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt),
            ],
        )

        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:].rstrip("```").strip()
        elif content.startswith("```"):
            content = content[3:].rstrip("```").strip()

        return json.loads(content)
    except Exception as e:
        return {
            "has_human_face": False,
            "face_clearly_visible": False,
            "lighting_adequate": False,
            "face_obstructed": False,
            "image_quality_score": 0.0,
            "issues": [f"Gemini call failed: {str(e)}"],
        }

def verify_face(image_bytes: bytes) -> tuple[bool, float, dict]:
    """
    Returns (is_verified, score, metadata)
    Raises HTTPException for multiple faces or no face.
    """
    opencv_result = detect_faces_opencv(image_bytes)
    
    if opencv_result["detected"] and opencv_result["face_count"] == 1:
        return True, opencv_result["confidence"], opencv_result
        
    elif opencv_result["face_count"] > 1:
        raise HTTPException(status_code=422, detail="MULTIPLE_FACES")
        
    else:
        # Fallback to Gemini
        gemini_result = verify_face_gemini(image_bytes)
        if gemini_result.get("has_human_face") and gemini_result.get("face_clearly_visible"):
            score = float(gemini_result.get("image_quality_score", 0.8))
            return True, score, gemini_result
        else:
            raise HTTPException(status_code=422, detail="FACE_NOT_DETECTED")
