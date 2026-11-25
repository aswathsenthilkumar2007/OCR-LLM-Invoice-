import unittest

from backend.app.services.invoice_extraction_service import preprocess_invoice_text


class PreprocessingTests(unittest.TestCase):
    def test_normalizes_whitespace_and_preserves_lines(self):
        result = preprocess_invoice_text("A  B\r\n\r\n\r\nC\tD")
        self.assertEqual(result, "A B\n\nC D")


if __name__ == "__main__":
    unittest.main()
