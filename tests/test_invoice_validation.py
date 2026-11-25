import unittest
from decimal import Decimal

from backend.app.services.invoice_validation_service import (
    to_decimal,
    validate_date,
    validate_invoice_data,
)


def make_invoice(**changes):
    invoice = {
        "supplier_name": "Example Supplier", "invoice_number": "INV-001",
        "invoice_date": "2026-11-20", "due_date": None,
        "subtotal": 30, "tax_amount": 3, "cgst": 1.5, "sgst": 1.5,
        "igst": None, "total_amount": 33,
        "line_items": [{"description": "Widget", "quantity": 2,
                        "unit_price": 15, "amount": 30}],
    }
    invoice.update(changes)
    return invoice


class InvoiceValidationTests(unittest.TestCase):
    def test_valid_invoice_is_approved(self):
        self.assertEqual(validate_invoice_data(make_invoice())["status"], "APPROVED")

    def test_missing_required_fields_needs_review(self):
        result = validate_invoice_data(make_invoice(invoice_number=None))
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertTrue(any("invoice_number" in message for message in result["errors"]))

    def test_incorrect_subtotal_and_total_need_review(self):
        result = validate_invoice_data(make_invoice(subtotal=31, total_amount=40))
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertTrue(any("Subtotal mismatch" in message for message in result["errors"]))
        self.assertTrue(any("Total amount mismatch" in message for message in result["errors"]))

    def test_missing_line_items_are_reported_as_skipped(self):
        result = validate_invoice_data(make_invoice(line_items=[]))
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(next(c for c in result["checks"]
                              if c["check"] == "line_item_calculation")["status"], "skipped")

    def test_ambiguous_date_is_not_valid(self):
        self.assertFalse(validate_date("02/03/2026"))
        self.assertFalse(validate_date("02.03.2026"))
        self.assertTrue(validate_date("13/03/2026"))
        result = validate_invoice_data(make_invoice(invoice_date="02/03/2026"))
        self.assertEqual(result["status"], "NEEDS_REVIEW")

    def test_currency_and_decimal_precision_parsing(self):
        self.assertEqual(to_decimal("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(to_decimal("(12.50)"), Decimal("-12.50"))
        self.assertIsNone(to_decimal("NaN"))


if __name__ == "__main__":
    unittest.main()
