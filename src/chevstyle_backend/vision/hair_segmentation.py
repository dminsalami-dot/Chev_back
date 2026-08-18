import io
import moondream as md
from PIL import Image

from chevstyle_backend.config import settings
from chevstyle_backend.schemas.image import HairSegmentationResult

def segment_hair(image_bytes: bytes) -> HairSegmentationResult:
    model = md.vl(api_key=settings.moondream_api_key)
    image = Image.open(io.BytesIO(image_bytes))

    result = model.segment(image, "hair")
    
    # We log as requested
    svg_path = result["path"]
    bbox = result["bbox"]
    print(f"SVG Path: {svg_path[:100]}...")
    print(f"Bounding box: {bbox}")

    return HairSegmentationResult(
        path=svg_path,
        bbox=bbox
    )
