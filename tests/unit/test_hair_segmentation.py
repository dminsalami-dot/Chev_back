import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import io

from chevstyle_backend.vision.hair_segmentation import segment_hair
from chevstyle_backend.schemas.image import HairSegmentationResult


class TestHairSegmentation(unittest.TestCase):
    def setUp(self):
        # Create a simple red 100x100 PNG image in memory for testing
        img = Image.new("RGB", (100, 100), color="red")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        self.valid_img_bytes = img_byte_arr.getvalue()

    @patch("chevstyle_backend.vision.hair_segmentation.settings")
    @patch("moondream.vl")
    def test_segment_hair_successful_response(self, mock_vl, mock_settings):
        # Mock successful segment response
        mock_settings.moondream_api_key = "fake-key"
        mock_model = MagicMock()
        
        mock_response = {
            "path": "M 0 0",
            "bbox": {
                "x_min": 0.1,
                "y_min": 0.2,
                "x_max": 0.6,
                "y_max": 0.8
            }
        }
        mock_model.segment.return_value = mock_response
        mock_vl.return_value = mock_model

        result = segment_hair(self.valid_img_bytes)

        self.assertEqual(result.path, "M 0 0")
        self.assertEqual(result.bbox.x_min, 0.1)
        self.assertEqual(result.bbox.y_min, 0.2)
        self.assertEqual(result.bbox.x_max, 0.6)
        self.assertEqual(result.bbox.y_max, 0.8)
