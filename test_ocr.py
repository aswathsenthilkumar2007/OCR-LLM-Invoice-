import io
import unittest
from unittest.mock import patch

from PIL import Image

from backend.app.services import ocr_service


class _FakeResult:
    json = {"res": {"rec_texts": ["sample invoice"]}}


class _FakeEngine:
    def predict(self, image):
        return [_FakeResult()]


class RootOCRTests(unittest.TestCase):
    def test_sample_image_service(self):
        stream = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(stream, format="PNG")
        with patch.object(ocr_service, "_get_ocr_engine", return_value=_FakeEngine()):
            result = ocr_service.extract_text_from_image(stream.getvalue())
        self.assertEqual(result["extracted_text"], "sample invoice")


if __name__ == "__main__":
    unittest.main()
