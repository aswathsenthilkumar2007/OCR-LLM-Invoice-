import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.main import app
from backend.app.routes import invoice_routes as routes
from backend.app.schemas import InvoiceRejectRequest, InvoiceUpdateRequest
from backend.app.services import duplicate_detection_service as service


def make_invoice(**changes):
    invoice = {
        "supplier_name": "Workflow Supplier", "supplier_gstin": None,
        "invoice_number": "WF-001", "po_number": None,
        "invoice_date": "2026-11-20", "due_date": None,
        "buyer_name": "Buyer", "buyer_gstin": None, "currency": "USD",
        "subtotal": 30, "tax_amount": 3, "cgst": None, "sgst": None,
        "igst": None, "total_amount": 33,
        "line_items": [{"description": "Widget", "quantity": 2,
                        "unit_price": 15, "amount": 30}],
    }
    invoice.update(changes)
    return invoice


class InvoiceReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir_patch = patch.object(service, "DATABASE_DIR", Path(self.temp.name))
        self.path_patch = patch.object(
            service, "DATABASE_PATH", Path(self.temp.name) / "review.sqlite3"
        )
        self.dir_patch.start()
        self.path_patch.start()
        service.initialize_database()

    def tearDown(self):
        self.path_patch.stop()
        self.dir_patch.stop()
        self.temp.cleanup()

    def seed(self, data=None, decision="PENDING"):
        data = make_invoice() if data is None else data
        validation = routes.validate_invoice_data(data)
        duplicate = {"status": "AVAILABLE", "is_duplicate": False,
                     "message": "No confirmed duplicate was found."}
        return str(service.save_invoice_document(
            "workflow.png", data, validation, duplicate,
            decision, "immutable OCR text", "clean OCR text",
        ))

    def count_registry(self):
        with closing(sqlite3.connect(service.DATABASE_PATH)) as connection, connection:
            return connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]

    def test_review_routes_are_registered_with_response_contracts(self):
        paths = app.openapi()["paths"]
        self.assertIn("patch", paths["/invoice/{invoice_id}"])
        self.assertIn("post", paths["/invoice/{invoice_id}/approve"])
        self.assertIn("post", paths["/invoice/{invoice_id}/reject"])

    def test_successful_invoice_edit_preserves_raw_ocr_text(self):
        invoice_id = self.seed()
        result = routes.edit_invoice(
            invoice_id, InvoiceUpdateRequest(currency="EUR", due_date="2026-12-20")
        )
        self.assertEqual(result["data"]["invoice_data"]["currency"], "EUR")
        self.assertEqual(result["data"]["raw_text"], "immutable OCR text")

    def test_invalid_field_update_is_rejected(self):
        invoice_id = self.seed()
        with self.assertRaises(HTTPException) as error:
            routes.edit_invoice(invoice_id, InvoiceUpdateRequest(invoice_date="02/03/2026"))
        self.assertEqual(error.exception.status_code, 422)

    def test_missing_invoice_edit_returns_404(self):
        with self.assertRaises(HTTPException) as error:
            routes.edit_invoice("999", InvoiceUpdateRequest(currency="EUR"))
        self.assertEqual(error.exception.status_code, 404)

    def test_successful_approval_registers_invoice(self):
        invoice_id = self.seed()
        result = routes.approve_invoice(invoice_id)
        self.assertEqual(result["data"]["review_status"], "APPROVED")
        self.assertEqual(self.count_registry(), 1)

    def test_approval_with_missing_mandatory_fields_is_rejected(self):
        invoice_id = self.seed(make_invoice(invoice_number=None), "NEEDS_REVIEW")
        with self.assertRaises(HTTPException) as error:
            routes.approve_invoice(invoice_id)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count_registry(), 0)

    def test_repeated_approval_is_idempotent(self):
        invoice_id = self.seed()
        routes.approve_invoice(invoice_id)
        second = routes.approve_invoice(invoice_id)
        self.assertEqual(second["data"]["review_status"], "APPROVED")
        self.assertEqual(self.count_registry(), 1)

    def test_duplicate_approval_returns_conflict(self):
        first_id = self.seed()
        routes.approve_invoice(first_id)
        second_id = self.seed()
        with self.assertRaises(HTTPException) as error:
            routes.approve_invoice(second_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count_registry(), 1)

    def test_successful_rejection_stores_reason(self):
        invoice_id = self.seed()
        result = routes.reject_invoice(
            invoice_id, InvoiceRejectRequest(reason="PO not attached")
        )
        self.assertEqual(result["data"]["review_status"], "REJECTED")
        self.assertEqual(result["data"]["rejection_reason"], "PO not attached")
        self.assertEqual(self.count_registry(), 0)

    def test_rejected_invoice_never_enters_duplicate_registry(self):
        invoice_id = self.seed()
        routes.reject_invoice(invoice_id)
        self.assertEqual(service.find_duplicate_invoice(make_invoice())["status"], "AVAILABLE")
        next_id = self.seed()
        result = service.approve_invoice_document(next_id)
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(self.count_registry(), 1)

    def test_approved_invoice_identity_cannot_be_changed(self):
        invoice_id = self.seed()
        routes.approve_invoice(invoice_id)
        with self.assertRaises(HTTPException) as error:
            routes.edit_invoice(invoice_id, InvoiceUpdateRequest(invoice_number="WF-002"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count_registry(), 1)

    def test_approved_invoice_non_key_edit_updates_registry_summary(self):
        invoice_id = self.seed()
        routes.approve_invoice(invoice_id)
        result = routes.edit_invoice(
            invoice_id,
            InvoiceUpdateRequest(
                subtotal=32, tax_amount=3, total_amount=35, currency="EUR",
                line_items=[{"description": "Widget", "quantity": 2,
                             "unit_price": 16, "amount": 32}],
            ),
        )
        self.assertEqual(result["data"]["review_status"], "APPROVED")
        self.assertEqual(result["data"]["raw_text"], "immutable OCR text")
        with closing(sqlite3.connect(service.DATABASE_PATH)) as connection, connection:
            registered_total = connection.execute(
                "SELECT total_amount FROM invoices"
            ).fetchone()[0]
        self.assertEqual(registered_total, "35.00")

    def test_approval_transaction_rolls_back_registry_on_failure(self):
        invoice_id = self.seed()
        with closing(sqlite3.connect(service.DATABASE_PATH)) as connection, connection:
            connection.execute("""CREATE TRIGGER fail_approval
                BEFORE UPDATE OF review_status ON invoice_documents
                WHEN NEW.review_status = 'APPROVED'
                BEGIN SELECT RAISE(ABORT, 'forced test failure'); END""")
        with self.assertRaises(HTTPException) as error:
            routes.approve_invoice(invoice_id)
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.count_registry(), 0)
        self.assertEqual(service.get_invoice_document(invoice_id)["review_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
