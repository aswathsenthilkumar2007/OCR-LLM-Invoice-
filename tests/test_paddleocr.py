import io
import unittest
from unittest.mock import patch

from PIL import Image

from backend.app.services import ocr_service


class FakeResult:
    json = {"res": {"rec_texts": ["Invoice 123", "Total 10.00"]}}


class FakeEngine:
    def predict(self, image):
        return [FakeResult()]


class PaddleOCRServiceTests(unittest.TestCase):
    def setUp(self):
        stream = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(stream, format="PNG")
        self.png = stream.getvalue()

    def test_image_ocr_result_parsing(self):
        with patch.object(ocr_service, "_get_ocr_engine", return_value=FakeEngine()):
            result = ocr_service.extract_text_from_image(self.png)
        self.assertEqual(result["extracted_text"], "Invoice 123\nTotal 10.00")

    def test_jpeg_image_is_supported(self):
        stream = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(stream, format="JPEG")
        with patch.object(ocr_service, "_get_ocr_engine", return_value=FakeEngine()):
            result = ocr_service.extract_text_from_image(stream.getvalue())
        self.assertIn("Invoice 123", result["extracted_text"])

    def test_unsupported_image_content_is_rejected(self):
        stream = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(stream, format="GIF")
        with self.assertRaisesRegex(ValueError, "Only PNG and JPEG"):
            ocr_service.extract_text_from_image(stream.getvalue())

    def test_corrupted_image_is_rejected(self):
        with self.assertRaises(ValueError):
            ocr_service.extract_text_from_image(b"not an image")

    def test_pdf_is_rendered_page_by_page(self):
        import fitz
        document = fitz.open()
        document.new_page(width=100, height=100)
        document.new_page(width=100, height=100)
        pdf_bytes = document.tobytes()
        document.close()
        calls = []

        def fake_image_ocr(page_bytes):
            calls.append(page_bytes)
            return {"extracted_text": f"text {len(calls)}"}

        with patch.object(ocr_service, "extract_text_from_image", side_effect=fake_image_ocr):
            result = ocr_service.extract_text_from_pdf(pdf_bytes)
        self.assertEqual(len(calls), 2)
        self.assertIn("--- Page 1 ---", result["extracted_text"])
        self.assertIn("--- Page 2 ---", result["extracted_text"])

    def test_corrupted_pdf_is_rejected(self):
        with self.assertRaises(ValueError):
            ocr_service.extract_text_from_pdf(b"%PDF-not-valid")

    def test_pdf_page_count_limit(self):
        import fitz
        document = fitz.open()
        for _ in range(ocr_service.MAX_PDF_PAGES + 1):
            document.new_page(width=10, height=10)
        pdf_bytes = document.tobytes()
        document.close()
        with self.assertRaisesRegex(ValueError, "page limit"):
            ocr_service.extract_text_from_pdf(pdf_bytes)


if __name__ == "__main__":
    unittest.main()
