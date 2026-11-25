
import sqlite3
import re
from pathlib import Path


# Store the database in the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATABASE_DIR / "invoices.db"


def normalize_value(value):
    """Normalize text for consistent duplicate comparison."""

    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).casefold()
    )


def initialize_database():
    """Create the database and invoice table if they don't exist."""

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_key TEXT NOT NULL,
                invoice_number_key TEXT NOT NULL,
                supplier_name TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                invoice_date TEXT,
                total_amount TEXT,
                filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(supplier_key, invoice_number_key)
            )
        """)


def check_and_register_invoice(invoice_data, filename=None):
    """
    Check whether an invoice already exists.

    If new:
        Register it in SQLite.

    If duplicate:
        Return the previously stored invoice details.
    """

    supplier_name = invoice_data.get("supplier_name")
    invoice_number = invoice_data.get("invoice_number")

    supplier_key = normalize_value(supplier_name)
    invoice_number_key = normalize_value(invoice_number)

    # Cannot perform reliable duplicate detection without identifiers
    if not supplier_key or not invoice_number_key:

        return {
            "status": "NOT_CHECKED",
            "is_duplicate": False,
            "message": (
                "Supplier name or invoice number is missing. "
                "Duplicate detection could not be performed."
            )
        }

    initialize_database()

    with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO invoices (
                supplier_key,
                invoice_number_key,
                supplier_name,
                invoice_number,
                invoice_date,
                total_amount,
                filename
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                supplier_key,
                invoice_number_key,
                str(supplier_name),
                str(invoice_number),
                invoice_data.get("invoice_date"),
                str(invoice_data.get("total_amount")),
                filename
            )
        )

        # New record successfully inserted
        if cursor.rowcount == 1:

            return {
                "status": "NEW",
                "is_duplicate": False,
                "message": "New invoice registered successfully."
            }

        # Existing invoice found
        existing = connection.execute(
            """
            SELECT
                id,
                supplier_name,
                invoice_number,
                invoice_date,
                total_amount,
                filename,
                created_at
            FROM invoices
            WHERE supplier_key = ?
              AND invoice_number_key = ?
            """,
            (supplier_key, invoice_number_key)
        ).fetchone()

        return {
            "status": "DUPLICATE",
            "is_duplicate": True,
            "message": "This invoice has already been processed.",
            "existing_invoice": {
                "id": existing[0],
                "supplier_name": existing[1],
                "invoice_number": existing[2],
                "invoice_date": existing[3],
                "total_amount": existing[4],
                "filename": existing[5],
                "created_at": existing[6]
            } if existing else None
        }
