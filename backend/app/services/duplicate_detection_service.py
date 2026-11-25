
import sqlite3
import re
import json
from contextlib import closing
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# Store database in project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATABASE_DIR / "invoices.db"


def normalize_value(value):
    """Normalize text for consistent comparison."""

    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).casefold()
    )


def normalize_invoice_date(value):
    """
    Normalize invoice dates to YYYY-MM-DD.

    Day-first interpretation is preferred for ambiguous
    DD/MM/YYYY dates, matching the existing extraction output.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
    ]

    for date_format in formats:
        try:
            parsed_date = datetime.strptime(value, date_format)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Preserve original value if it cannot be parsed
    return value


def normalize_amount(value):
    """Normalize monetary amounts using Decimal."""

    if value is None:
        return None

    try:
        amount = str(value).strip()

        if not amount:
            return None

        # Handle accounting-style negative amounts
        negative = amount.startswith("(") and amount.endswith(")")

        amount = amount.strip("()")
        amount = re.sub(r"[^\d.\-]", "", amount)

        if not amount:
            return None

        decimal_value = Decimal(amount)

        if negative:
            decimal_value = -abs(decimal_value)

        decimal_value = decimal_value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        return format(decimal_value, ".2f")

    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def initialize_database():
    """Create database and invoice table if necessary."""

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:

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
        # Keep the duplicate registry intact; upload history is stored in an
        # additive table so review and duplicate attempts remain visible.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoice_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                invoice_data_json TEXT NOT NULL,
                validation_json TEXT NOT NULL,
                duplicate_json TEXT NOT NULL,
                processing_decision TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                cleaned_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                review_status TEXT,
                rejection_reason TEXT,
                updated_at TIMESTAMP
            )
        """)
        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(invoice_documents)")
        }
        # Nullable, additive columns preserve all existing history rows.
        for column, column_type in (
            ("review_status", "TEXT"),
            ("rejection_reason", "TEXT"),
            ("updated_at", "TIMESTAMP"),
        ):
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE invoice_documents ADD COLUMN {column} {column_type}"
                )


def save_invoice_document(filename, invoice_data, validation, duplicate_result,
                          processing_decision, raw_text, cleaned_text):
    """Persist a processing attempt without changing duplicate eligibility."""
    initialize_database()
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        cursor = connection.execute(
            """INSERT INTO invoice_documents
               (filename, invoice_data_json, validation_json, duplicate_json,
                processing_decision, raw_text, cleaned_text, review_status,
                updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (filename, json.dumps(invoice_data, ensure_ascii=False),
             json.dumps(validation, ensure_ascii=False),
             json.dumps(duplicate_result, ensure_ascii=False),
             processing_decision, raw_text, cleaned_text,
             _initial_review_status(processing_decision)),
        )
        return cursor.lastrowid


def list_invoice_documents(limit=50, offset=0):
    """List processed uploads plus existing registry rows from older versions."""
    initialize_database()
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        documents = connection.execute(
            """SELECT id, filename, invoice_data_json, validation_json,
                      duplicate_json, processing_decision, created_at,
                      review_status, rejection_reason, updated_at
               FROM invoice_documents ORDER BY id DESC""",
        ).fetchall()
        total = connection.execute("SELECT COUNT(*) FROM invoice_documents").fetchone()[0]
        results = [_document_summary(row) for row in documents]
        confirmed_keys = {
            (
                normalize_value(item["invoice_data"].get("supplier_name")),
                normalize_value(item["invoice_data"].get("invoice_number")),
            )
            for item in results
            if item["processing_decision"] == "APPROVED"
        }

        # Preserve dashboard visibility for records predating upload history.
        legacy = connection.execute(
            """SELECT id, supplier_name, invoice_number, invoice_date,
                      total_amount, filename, created_at
               FROM invoices ORDER BY id DESC"""
        ).fetchall()
        legacy_records = [{
            "id": f"legacy_{row['id']}", "filename": row['filename'],
            "invoice_data": {"supplier_name": row['supplier_name'],
                             "invoice_number": row['invoice_number'],
                             "invoice_date": row['invoice_date'],
                             "total_amount": row['total_amount']},
            "validation": None, "duplicate_detection": None,
            "processing_decision": "APPROVED", "created_at": row['created_at'],
            "review_status": "APPROVED", "rejection_reason": None,
        } for row in legacy if (
            normalize_value(row["supplier_name"]),
            normalize_value(row["invoice_number"]),
        ) not in confirmed_keys]
        results.extend(legacy_records)
        results.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return results[offset:offset + limit], total + len(legacy_records)


def get_invoice_document(document_id):
    """Get a processed upload or a preserved legacy registry record."""
    initialize_database()
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        if str(document_id).startswith("legacy_"):
            raw_id = str(document_id)[7:]
            if not raw_id.isdigit():
                return None
            row = connection.execute(
                """SELECT id, supplier_name, invoice_number, invoice_date,
                          total_amount, filename, created_at
                   FROM invoices WHERE id = ?""", (int(raw_id),)
            ).fetchone()
            if not row:
                return None
            return {
                "id": f"legacy_{row['id']}", "filename": row['filename'],
                "invoice_data": {"supplier_name": row['supplier_name'],
                                 "invoice_number": row['invoice_number'],
                                 "invoice_date": row['invoice_date'],
                                 "total_amount": row['total_amount']},
                "validation": None, "duplicate_detection": None,
                "processing_decision": "APPROVED", "created_at": row['created_at'],
                "review_status": "APPROVED", "rejection_reason": None,
            }
        try:
            parsed_id = int(document_id)
        except (TypeError, ValueError):
            return None
        row = connection.execute(
            """SELECT id, filename, invoice_data_json, validation_json,
                      duplicate_json, processing_decision, raw_text, cleaned_text,
                      created_at, review_status, rejection_reason, updated_at
               FROM invoice_documents WHERE id = ?""",
            (parsed_id,),
        ).fetchone()
        if not row:
            return None
        return {
            **_document_summary(row), "raw_text": row['raw_text'],
            "cleaned_text": row['cleaned_text'],
        }


def _document_summary(row):
    return {
        "id": str(row['id']), "filename": row['filename'],
        "invoice_data": json.loads(row['invoice_data_json']),
        "validation": json.loads(row['validation_json']),
        "duplicate_detection": json.loads(row['duplicate_json']),
        "processing_decision": row['processing_decision'],
        "created_at": row['created_at'],
        "review_status": row['review_status'] or _initial_review_status(
            row['processing_decision']
        ),
        "rejection_reason": row['rejection_reason'],
    }


def _initial_review_status(processing_decision):
    if processing_decision == "DUPLICATE":
        return "NEEDS_REVIEW"
    if processing_decision in {"APPROVED", "REJECTED", "NEEDS_REVIEW"}:
        return processing_decision
    return "PENDING"


def find_duplicate_invoice(invoice_data):
    """Check the confirmed registry without registering a pending upload."""
    keys = (normalize_value(invoice_data.get("supplier_name")),
            normalize_value(invoice_data.get("invoice_number")))
    if not all(keys):
        return {"status": "NOT_CHECKED", "is_duplicate": False,
                "message": "Supplier name or invoice number is missing."}
    initialize_database()
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        existing = _existing_invoice(connection, keys)
        return _duplicate_result(existing) if existing else {
            "status": "AVAILABLE", "is_duplicate": False,
            "message": "No confirmed duplicate was found.",
        }


def update_invoice_document(document_id, updates):
    """Update invoice fields atomically while leaving original OCR text intact."""
    if str(document_id).startswith("legacy_") or not str(document_id).isdigit():
        return {"status": "NOT_FOUND"}
    initialize_database()
    from backend.app.services.invoice_validation_service import validate_invoice_data

    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        if row is None:
            return {"status": "NOT_FOUND"}
        old_data = json.loads(row["invoice_data_json"])
        status = row["review_status"] or _initial_review_status(row["processing_decision"])
        if status == "REJECTED":
            return {"status": "REJECTED"}
        updated_data = {**old_data, **updates}
        old_keys = (normalize_value(old_data.get("supplier_name")),
                    normalize_value(old_data.get("invoice_number")))
        new_keys = (normalize_value(updated_data.get("supplier_name")),
                    normalize_value(updated_data.get("invoice_number")))
        if status == "APPROVED" and old_keys != new_keys:
            return {"status": "APPROVED_KEY_CHANGE"}

        validation = validate_invoice_data(updated_data)
        if status == "APPROVED" and validation["status"] != "APPROVED":
            return {"status": "INVALID_APPROVED_EDIT", "validation": validation}

        if status == "APPROVED":
            cursor = connection.execute(
                """UPDATE invoices SET supplier_name = ?, invoice_number = ?,
                          invoice_date = ?, total_amount = ?
                   WHERE supplier_key = ? AND invoice_number_key = ?""",
                (str(updated_data.get("supplier_name")).strip(),
                 str(updated_data.get("invoice_number")).strip(),
                 normalize_invoice_date(updated_data.get("invoice_date")),
                 normalize_amount(updated_data.get("total_amount")), *old_keys),
            )
            if cursor.rowcount == 0:
                return {"status": "REGISTRY_MISSING"}
            duplicate = json.loads(row["duplicate_json"])
            review_status = decision = "APPROVED"
        else:
            duplicate = _find_duplicate_on_connection(connection, new_keys)
            if duplicate["is_duplicate"]:
                review_status, decision = "NEEDS_REVIEW", "DUPLICATE"
            elif validation["status"] != "APPROVED" or not all(new_keys):
                review_status, decision = "NEEDS_REVIEW", "NEEDS_REVIEW"
            else:
                review_status = decision = "PENDING"

        connection.execute(
            """UPDATE invoice_documents
               SET invoice_data_json = ?, validation_json = ?, duplicate_json = ?,
                   processing_decision = ?, review_status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (json.dumps(updated_data, ensure_ascii=False),
             json.dumps(validation, ensure_ascii=False),
             json.dumps(duplicate, ensure_ascii=False), decision, review_status,
             int(document_id)),
        )
        updated_row = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        return {"status": "UPDATED", "invoice": _document_detail(updated_row)}


def approve_invoice_document(document_id):
    """Revalidate and register the duplicate key in one serialized transaction."""
    if str(document_id).startswith("legacy_") or not str(document_id).isdigit():
        return {"status": "NOT_FOUND"}
    initialize_database()
    from backend.app.services.invoice_validation_service import validate_invoice_data

    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        if row is None:
            return {"status": "NOT_FOUND"}
        status = row["review_status"] or _initial_review_status(row["processing_decision"])
        if status == "APPROVED":
            return {"status": "ALREADY_APPROVED", "invoice": _document_detail(row)}
        if status == "REJECTED":
            return {"status": "REJECTED"}

        invoice_data = json.loads(row["invoice_data_json"])
        validation = validate_invoice_data(invoice_data)
        keys = (normalize_value(invoice_data.get("supplier_name")),
                normalize_value(invoice_data.get("invoice_number")))
        if validation["status"] != "APPROVED" or not all(keys):
            if not all(keys) and not any(
                "supplier_name" in error or "invoice_number" in error
                for error in validation["errors"]
            ):
                validation["errors"].append(
                    "Supplier name and invoice number are required for approval."
                )
            validation["status"] = "NEEDS_REVIEW"
            return {"status": "INVALID", "validation": validation}

        existing = _existing_invoice(connection, keys)
        if existing:
            duplicate = _duplicate_result(existing)
            connection.execute(
                """UPDATE invoice_documents SET duplicate_json = ?,
                          processing_decision = 'DUPLICATE',
                          review_status = 'NEEDS_REVIEW', updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (json.dumps(duplicate, ensure_ascii=False), int(document_id)),
            )
            updated = connection.execute(
                "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
            ).fetchone()
            return {"status": "DUPLICATE", "invoice": _document_detail(updated),
                    "duplicate_detection": duplicate}

        cursor = connection.execute(
            """INSERT OR IGNORE INTO invoices
               (supplier_key, invoice_number_key, supplier_name, invoice_number,
                invoice_date, total_amount, filename)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (*keys, str(invoice_data["supplier_name"]).strip(),
             str(invoice_data["invoice_number"]).strip(),
             normalize_invoice_date(invoice_data.get("invoice_date")),
             normalize_amount(invoice_data.get("total_amount")), row["filename"]),
        )
        if cursor.rowcount != 1:
            # Unique constraint is the final race guard in addition to BEGIN IMMEDIATE.
            existing = _existing_invoice(connection, keys)
            return {"status": "DUPLICATE", "duplicate_detection": _duplicate_result(existing)}

        duplicate = {"status": "NEW", "is_duplicate": False,
                     "message": "Invoice approved and registered."}
        connection.execute(
            """UPDATE invoice_documents SET validation_json = ?, duplicate_json = ?,
                      processing_decision = 'APPROVED', review_status = 'APPROVED',
                      rejection_reason = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (json.dumps(validation, ensure_ascii=False),
             json.dumps(duplicate, ensure_ascii=False), int(document_id)),
        )
        updated = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        return {"status": "APPROVED", "invoice": _document_detail(updated)}


def reject_invoice_document(document_id, reason=None):
    """Reject an unapproved document; rejection never adds a registry row."""
    if str(document_id).startswith("legacy_") or not str(document_id).isdigit():
        return {"status": "NOT_FOUND"}
    initialize_database()
    with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        if row is None:
            return {"status": "NOT_FOUND"}
        status = row["review_status"] or _initial_review_status(row["processing_decision"])
        if status == "APPROVED":
            return {"status": "ALREADY_APPROVED"}
        if status == "REJECTED":
            return {"status": "ALREADY_REJECTED", "invoice": _document_detail(row)}
        connection.execute(
            """UPDATE invoice_documents SET review_status = 'REJECTED',
                      processing_decision = 'REJECTED', rejection_reason = ?,
                      updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (reason, int(document_id)),
        )
        updated = connection.execute(
            "SELECT * FROM invoice_documents WHERE id = ?", (int(document_id),)
        ).fetchone()
        return {"status": "REJECTED", "invoice": _document_detail(updated)}


def _existing_invoice(connection, keys):
    return connection.execute(
        """SELECT id, supplier_name, invoice_number, invoice_date,
                  total_amount, filename, created_at
           FROM invoices WHERE supplier_key = ? AND invoice_number_key = ?""", keys
    ).fetchone()


def _find_duplicate_on_connection(connection, keys):
    if not all(keys):
        return {"status": "NOT_CHECKED", "is_duplicate": False,
                "message": "Supplier name or invoice number is missing."}
    existing = _existing_invoice(connection, keys)
    return _duplicate_result(existing) if existing else {
        "status": "AVAILABLE", "is_duplicate": False,
        "message": "No confirmed duplicate was found.",
    }


def _document_detail(row):
    return {**_document_summary(row), "raw_text": row["raw_text"],
            "cleaned_text": row["cleaned_text"]}


def check_and_register_invoice(
    invoice_data, filename=None, validation_status="APPROVED"
):
    """Compatibility duplicate check; registration is reserved for approval."""
    result = find_duplicate_invoice(invoice_data)
    if result["status"] == "AVAILABLE":
        return {
            "status": "NOT_REGISTERED", "is_duplicate": False,
            "message": "Invoice has not been approved and was not registered.",
        }
    return result


def _duplicate_result(existing):
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
            "created_at": existing[6],
        } if existing else None,
    }
