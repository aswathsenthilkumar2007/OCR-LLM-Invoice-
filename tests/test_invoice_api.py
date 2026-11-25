import asyncio
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from backend.app.routes import invoice_routes as routes
from backend.app.schemas import InvoiceDetailEnvelope, InvoiceUploadResponse
from backend.app.services import duplicate_detection_service as db_service
from backend.app.services import ocr_service


def valid_invoice(**changes):
    data = {
        "supplier_name": "API Test Supplier", "supplier_gstin": None,
        "invoice_number": "API-100", "po_number": None,
        "invoice_date": "2026-11-20", "due_date": None,
        "buyer_name": "Buyer", "buyer_gstin": None, "currency": "USD",
        "subtotal": 30, "tax_amount": 3, "cgst": None, "sgst": None,
        "igst": None, "total_amount": 33,
        "line_items": [{"description": "Widget", "quantity": 2,
                        "unit_price": 15, "amount": 30}],
    }
    data.update(changes)
    return data


def image_bytes(fmt):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format=fmt)
    return buffer.getvalue()


def make_upload(filename, content_type, content):
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


class InvoiceAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_dir_patch = patch.object(db_service, "DATABASE_DIR", Path(self.temp.name))
        self.db_path_patch = patch.object(
            db_service, "DATABASE_PATH", Path(self.temp.name) / "api_test.sqlite3"
        )
        self.db_dir_patch.start()
        self.db_path_patch.start()
        db_service.initialize_database()
        self.ocr_patch = patch.object(
            routes, "extract_text_from_image",
            side_effect=lambda _data: {"extracted_text": "sample invoice text"},
        )
        self.ocr_patch.start()
        self.gemini_patch = patch.object(routes, "extract_invoice_data", return_value=valid_invoice())
        self.gemini_patch.start()

    def tearDown(self):
        self.gemini_patch.stop()
        self.ocr_patch.stop()
        self.db_path_patch.stop()
        self.db_dir_patch.stop()
        self.temp.cleanup()

    def upload(self, filename="invoice.png", content_type="image/png", content=None):
        if content is None:
            content = image_bytes("PNG")
        result = asyncio.run(routes.upload_invoice(
            make_upload(filename, content_type, content)
        ))
        InvoiceUploadResponse.model_validate(result)
        return result

    def test_valid_png_upload(self):
        result = self.upload()
        self.assertEqual(result["processing_decision"], "PENDING")
        with closing(sqlite3.connect(db_service.DATABASE_PATH)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)

    def test_jpg_and_jpeg_uploads(self):
        jpg = image_bytes("JPEG")
        self.assertEqual(self.upload("one.jpg", "image/jpeg", jpg)["status"], "success")
        self.assertEqual(self.upload("two.jpeg", "image/jpeg", jpg)["status"], "success")

    def test_exact_duplicate_upload(self):
        first = self.upload()
        routes.approve_invoice(first["invoice_id"])
        result = self.upload()
        self.assertEqual(result["duplicate_detection"]["status"], "DUPLICATE")
        self.assertEqual(result["processing_decision"], "DUPLICATE")

    def test_review_upload_is_listed_but_not_confirmed(self):
        self.gemini_patch.stop()
        self.gemini_patch = patch.object(
            routes, "extract_invoice_data", return_value=valid_invoice(invoice_number=None)
        )
        self.gemini_patch.start()
        result = self.upload()
        self.assertEqual(result["validation"]["status"], "NEEDS_REVIEW")
        self.assertEqual(result["duplicate_detection"]["status"], "NOT_CHECKED")
        with closing(sqlite3.connect(db_service.DATABASE_PATH)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)
        self.assertEqual(routes.list_invoices(limit=50, offset=0)["total"], 1)

    def test_incorrect_totals_and_missing_line_items_are_visible(self):
        self.gemini_patch.stop()
        self.gemini_patch = patch.object(
            routes, "extract_invoice_data",
            return_value=valid_invoice(subtotal=31, total_amount=40, line_items=[]),
        )
        self.gemini_patch.start()
        result = self.upload()
        self.assertEqual(result["validation"]["status"], "NEEDS_REVIEW")
        self.assertTrue(any("Total amount mismatch" in message
                            for message in result["validation"]["errors"]))

    def test_ambiguous_date_requires_review(self):
        self.gemini_patch.stop()
        self.gemini_patch = patch.object(
            routes, "extract_invoice_data",
            return_value=valid_invoice(invoice_date="02/03/2026"),
        )
        self.gemini_patch.start()
        self.assertEqual(self.upload()["validation"]["status"], "NEEDS_REVIEW")

    def test_pdf_upload_converts_each_page_and_retains_result(self):
        pdf = fitz.open()
        pdf.new_page(width=100, height=100)
        pdf.new_page(width=100, height=100)
        pdf_bytes = pdf.tobytes()
        pdf.close()
        calls = []

        def fake_page_ocr(_page_bytes):
            calls.append(True)
            return {"extracted_text": f"Page text {len(calls)}"}

        with patch.object(ocr_service, "extract_text_from_image", side_effect=fake_page_ocr):
            result = self.upload("invoice.pdf", "application/pdf", pdf_bytes)
        self.assertEqual(len(calls), 2)
        self.assertIn("Page text 1", result["raw_text"])
        self.assertIn("Page text 2", result["raw_text"])

    def test_corrupt_image_and_pdf_are_rejected(self):
        with patch.object(routes, "extract_text_from_image",
                          side_effect=ocr_service.extract_text_from_image):
            with self.assertRaises(HTTPException) as image_error:
                self.upload("bad.png", "image/png", b"not an image")
            self.assertEqual(image_error.exception.status_code, 422)

        with self.assertRaises(HTTPException) as pdf_error:
            self.upload("bad.pdf", "application/pdf", b"%PDF-not-valid")
        self.assertEqual(pdf_error.exception.status_code, 422)

    def test_unsupported_format_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.upload("bad.gif", "image/gif", b"GIF89a")
        self.assertEqual(error.exception.status_code, 415)

    def test_upload_size_limit(self):
        with self.assertRaises(HTTPException) as error:
            self.upload("large.png", "image/png", b"x" * (routes.MAX_UPLOAD_BYTES + 1))
        self.assertEqual(error.exception.status_code, 413)

    def test_listing_and_detail_retrieval(self):
        uploaded = self.upload()
        listing = routes.list_invoices(limit=50, offset=0)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["data"][0]["id"], uploaded["invoice_id"])
        detail = routes.invoice_details(uploaded["invoice_id"])
        InvoiceDetailEnvelope.model_validate(detail)
        self.assertEqual(detail["data"]["invoice_data"]["invoice_number"], "API-100")
        with self.assertRaises(HTTPException) as error:
            routes.invoice_details("999999")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
