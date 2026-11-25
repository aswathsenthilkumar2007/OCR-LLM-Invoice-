import unittest

from backend.app.services.duplicate_detection_service import (
    normalize_amount,
    normalize_invoice_date,
    normalize_value,
)


class DuplicateNormalizationTests(unittest.TestCase):
    def test_invoice_date_normalization(self):
        self.assertEqual(normalize_invoice_date("2019-02-11"), "2019-02-11")
        self.assertEqual(normalize_invoice_date("11/02/2019"), "2019-02-11")

    def test_amount_normalization(self):
        self.assertEqual(normalize_amount("154.060"), "154.06")
        self.assertEqual(normalize_amount("$154.06"), "154.06")

    def test_text_normalization(self):
        self.assertEqual(normalize_value("US-001"), normalize_value("us 001"))


if __name__ == "__main__":
    unittest.main()
