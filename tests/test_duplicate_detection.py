import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.app.services import duplicate_detection_service as service
from backend.app.services.invoice_validation_service import validate_invoice_data


def invoice_data(**changes):
    invoice = {
        "supplier_name": "Test Supplier Ltd", "invoice_number": "INV-42",
        "invoice_date": "2026-02-10", "due_date": None, "subtotal": 15,
        "tax_amount": 0, "total_amount": 15, "line_items": [
            {"description": "Test item", "quantity": 1,
             "unit_price": 15, "amount": 15}
        ],
    }
    invoice.update(changes)
    return invoice


class DuplicateDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_dir = patch.object(service, "DATABASE_DIR", Path(self.temp.name))
        self.database_path = patch.object(
            service, "DATABASE_PATH", Path(self.temp.name) / "isolated.sqlite3"
        )
        self.database_dir.start()
        self.database_path.start()
        service.initialize_database()

    def tearDown(self):
        self.database_path.stop()
        self.database_dir.stop()
        self.temp.cleanup()

    def test_new_invoice_and_exact_normalized_duplicate(self):
        invoice = invoice_data()
        self.assertEqual(service.find_duplicate_invoice(invoice)["status"], "AVAILABLE")
        first_id = self._seed(invoice)
        first = service.approve_invoice_document(first_id)
        duplicate_id = self._seed(invoice_data(
            supplier_name="test supplier ltd", invoice_number="inv42"
        ))
        duplicate = service.approve_invoice_document(duplicate_id)
        self.assertEqual(first["status"], "APPROVED")
        self.assertEqual(duplicate["status"], "DUPLICATE")
        self.assertTrue(duplicate["duplicate_detection"]["is_duplicate"])

    def test_review_invoice_is_not_registered_and_does_not_block_later_approval(self):
        invoice = invoice_data()
        review = service.check_and_register_invoice(invoice, validation_status="NEEDS_REVIEW")
        self.assertEqual(review["status"], "NOT_REGISTERED")
        document_id = self._seed(invoice, "NEEDS_REVIEW")
        approved = service.approve_invoice_document(document_id)
        self.assertEqual(approved["status"], "APPROVED")

    def _seed(self, invoice, decision="PENDING"):
        validation = validate_invoice_data(invoice)
        duplicate = {"status": "AVAILABLE", "is_duplicate": False,
                     "message": "No confirmed duplicate was found."}
        return str(service.save_invoice_document(
            "test.png", invoice, validation, duplicate, decision, "raw", "clean"
        ))

    def test_missing_identifiers_are_not_checked(self):
        result = service.check_and_register_invoice(
            {"supplier_name": "Supplier", "invoice_number": None},
            validation_status="APPROVED",
        )
        self.assertEqual(result["status"], "NOT_CHECKED")

    def test_invoice_history_supports_list_and_detail(self):
        invoice = {"supplier_name": "History Supplier", "invoice_number": "H-1"}
        validation = {"status": "NEEDS_REVIEW", "errors": ["bad total"], "warnings": [], "checks": []}
        duplicate = {"status": "NOT_REGISTERED", "is_duplicate": False,
                     "message": "needs review"}
        document_id = service.save_invoice_document(
            "review.png", invoice, validation, duplicate, "NEEDS_REVIEW", "raw", "clean"
        )
        rows, total = service.list_invoice_documents()
        detail = service.get_invoice_document(str(document_id))
        self.assertGreaterEqual(total, 1)
        self.assertEqual(rows[0]["id"], str(document_id))
        self.assertEqual(detail["validation"]["errors"], ["bad total"])
        self.assertEqual(detail["raw_text"], "raw")

    def test_additive_workflow_migration_preserves_existing_document_values(self):
        old_database = Path(self.temp.name) / "old_schema.sqlite3"
        with patch.object(service, "DATABASE_PATH", old_database):
            with closing(sqlite3.connect(old_database)) as connection, connection:
                connection.execute("""CREATE TABLE invoice_documents (
                    id INTEGER PRIMARY KEY, filename TEXT,
                    invoice_data_json TEXT NOT NULL, validation_json TEXT NOT NULL,
                    duplicate_json TEXT NOT NULL, processing_decision TEXT NOT NULL,
                    raw_text TEXT NOT NULL, cleaned_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
                connection.execute(
                    """INSERT INTO invoice_documents
                       (id, filename, invoice_data_json, validation_json, duplicate_json,
                        processing_decision, raw_text, cleaned_text)
                       VALUES (1, 'old.png', '{}', '{}', '{}', 'NEEDS_REVIEW', 'keep raw', 'keep clean')"""
                )
            service.initialize_database()
            with closing(sqlite3.connect(old_database)) as connection, connection:
                row = connection.execute(
                    "SELECT raw_text, cleaned_text, review_status FROM invoice_documents WHERE id = 1"
                ).fetchone()
        self.assertEqual(row, ("keep raw", "keep clean", None))


if __name__ == "__main__":
    unittest.main()
