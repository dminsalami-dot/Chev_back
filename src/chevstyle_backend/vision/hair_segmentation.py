import cv2
import numpy as np

from chevstyle_backend.schemas.image import BoundingBox, HairSegmentationResult

# Re-use the same cascade already loaded in face_verification
CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(CASCADE_PATH)


def segment_hair(image_bytes: bytes) -> HairSegmentationResult:
    """
    Identifies the hair region in the photo and returns a bounding box.

    Approach (TRD §7.2):
    - Detect the face with OpenCV Haar Cascade (lightweight, no network call).
    - Derive the hair bounding box by extending upward from the face:
        hair_y  = face_y - 65 % of face height (above eyebrows)
        hair_h  = 70 % of face height  (from top of hair to mid-forehead)
        hair_x  = face_x - 15 % of face width (slightly wider than face)
        hair_w  = face_w + 30 % (symmetric horizontal padding)
    - If no face is found, return a zero bounding box with confidence 0.
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return HairSegmentationResult(
            bounding_box=BoundingBox(x=0, y=0, width=0, height=0),
            confidence=0.0,
        )

    ih, iw = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )

    if len(faces) == 0:
        return HairSegmentationResult(
            bounding_box=BoundingBox(x=0, y=0, width=0, height=0),
            confidence=0.0,
        )

    # Use the largest detected face
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces[0]

    # --- Hair region estimation ---
    hair_x = max(0, x - int(w * 0.15))
    hair_w = min(iw - hair_x, int(w * 1.30))

    hair_y = max(0, y - int(h * 0.65))
    hair_h = min(ih - hair_y, int(h * 0.70))

    # Confidence proxy: ratio of face area to image area (higher → more reliable)
    face_area_ratio = (w * h) / (iw * ih)
    confidence = min(0.95, 0.5 + face_area_ratio * 10)

    return HairSegmentationResult(
        bounding_box=BoundingBox(x=hair_x, y=hair_y, width=hair_w, height=hair_h),
        confidence=round(confidence, 4),
    )
