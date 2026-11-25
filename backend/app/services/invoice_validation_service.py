
from datetime import datetime
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_decimal(value):
    """Safely convert extracted values into Decimal."""
    try:
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        if not text:
            return None
        negative = text.startswith("(") and text.endswith(")")
        text = text.strip("()")
        text = re.sub(r"[^0-9,.+\-]", "", text)
        # Treat a lone comma as a decimal separator only when it has 1-2
        # trailing digits; otherwise treat commas as thousands separators.
        if "," in text and "." not in text:
            if re.search(r",\d{1,2}$", text):
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", "")
        number = Decimal(text)
        if not number.is_finite() or abs(number) >= Decimal("1e15"):
            return None
        return -abs(number) if negative else number
    except (InvalidOperation, ValueError, TypeError):
        return None


def validate_date(value):
    """Check whether a date follows a recognized format."""
    if not value:
        return False

    value = str(value).strip()
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"]

    # Numeric day/month dates are accepted only when their order is clear.
    for separator in ("/", "-", "."):
        parts = value.split(separator)
        if len(parts) == 3 and len(parts[2]) == 4:
            try:
                first, second, year = map(int, parts)
                if first <= 12 and second <= 12 and first != second:
                    return False
                if first <= 12 and second > 12:
                    date_format = f"%m{separator}%d{separator}%Y"
                else:
                    date_format = f"%d{separator}%m{separator}%Y"
                datetime.strptime(value, date_format)
                return True
            except (ValueError, TypeError):
                pass

    for date_format in formats:
        try:
            datetime.strptime(value, date_format)
            return True
        except (ValueError, AttributeError):
            continue

    return False


def validate_invoice_data(invoice_data):
    errors = []
    warnings = []
    checks = []

    def add_check(name, passed, message):
        checks.append({
            "check": name,
            "status": "passed" if passed else "failed",
            "message": message
        })

    # 1. Mandatory field validation
    required_fields = [
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "subtotal",
        "tax_amount",
        "total_amount"
    ]

    missing_fields = [
        field for field in required_fields
        if invoice_data.get(field) is None
        or (isinstance(invoice_data.get(field), str)
            and not invoice_data.get(field).strip())
    ]

    if missing_fields:
        errors.append(
            f"Missing required fields: {', '.join(missing_fields)}"
        )

    add_check(
        "mandatory_fields",
        len(missing_fields) == 0,
        "All mandatory fields are present."
        if not missing_fields
        else f"Missing: {', '.join(missing_fields)}"
    )

    # 2. Invoice date validation
    invoice_date = invoice_data.get("invoice_date")

    date_valid = validate_date(invoice_date)

    if not date_valid:
        warnings.append(
            f"Invalid or unrecognized invoice date: {invoice_date}"
        )

    add_check(
        "invoice_date",
        date_valid,
        "Invoice date is valid."
        if date_valid
        else "Invoice date requires manual verification."
    )

    # 3. Due date validation
    due_date = invoice_data.get("due_date")

    if due_date:
        due_date_valid = validate_date(due_date)

        if not due_date_valid:
            warnings.append(
                f"Invalid or unrecognized due date: {due_date}"
            )

        add_check(
            "due_date",
            due_date_valid,
            "Due date is valid."
            if due_date_valid
            else "Due date requires manual verification."
        )

    # 4. Line-item calculation validation
    line_items = invoice_data.get("line_items") or []
    calculated_subtotal = Decimal("0.00")
    line_items_valid = True
    line_items_complete = bool(line_items)

    for index, item in enumerate(line_items, start=1):
        if not isinstance(item, dict):
            line_items_valid = False
            line_items_complete = False
            errors.append(f"Line item {index}: Invalid item structure.")
            continue

        if not str(item.get("description") or "").strip():
            line_items_valid = False
            line_items_complete = False
            errors.append(f"Line item {index}: Description is missing.")

        quantity = to_decimal(item.get("quantity"))
        unit_price = to_decimal(item.get("unit_price"))
        amount = to_decimal(item.get("amount"))

        if quantity is None or unit_price is None or amount is None:
            line_items_valid = False
            line_items_complete = False
            errors.append(
                f"Line item {index}: Missing or invalid numeric values."
            )
            continue

        raw_expected_amount = quantity * unit_price
        if abs(raw_expected_amount) >= Decimal("1e15"):
            line_items_valid = False
            line_items_complete = False
            errors.append(f"Line item {index}: Calculated amount is out of range.")
            continue

        expected_amount = raw_expected_amount.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        rounded_amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if abs(expected_amount - rounded_amount) > Decimal("0.01"):
            line_items_valid = False
            errors.append(
                f"Line item {index}: Expected amount "
                f"{expected_amount}, but extracted amount is {amount}."
            )

        calculated_subtotal += rounded_amount

    if line_items:
        add_check(
            "line_item_calculation",
            line_items_valid,
            "All line-item calculations match."
            if line_items_valid
            else "One or more line-item calculations do not match."
        )
    else:
        checks.append({"check": "line_item_calculation", "status": "skipped",
                       "message": "No line items were extracted."})

    # 5. Subtotal validation
    extracted_subtotal = to_decimal(invoice_data.get("subtotal"))

    subtotal_valid = (
        extracted_subtotal is not None
        and line_items_complete
        and abs(calculated_subtotal - extracted_subtotal.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )) <= Decimal("0.01")
    )

    if line_items_complete and extracted_subtotal is not None and not subtotal_valid:
        errors.append(
            f"Subtotal mismatch: Line items total "
            f"{calculated_subtotal}, extracted subtotal "
            f"{extracted_subtotal}."
        )

    if line_items:
        add_check(
            "subtotal_validation", subtotal_valid,
            "Subtotal matches the line items." if subtotal_valid
            else "Subtotal does not match the line-item amounts."
        )
    else:
        checks.append({"check": "subtotal_validation", "status": "skipped",
                       "message": "No line items were available to compare."})

    # 6. Tax and total validation
    tax_amount = to_decimal(invoice_data.get("tax_amount"))
    total_amount = to_decimal(invoice_data.get("total_amount"))

    total_valid = (
        extracted_subtotal is not None
        and tax_amount is not None
        and total_amount is not None
        and abs((extracted_subtotal + tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) - total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) <= Decimal("0.01")
    )

    if not total_valid:
        errors.append(
            "Total amount mismatch or missing financial values."
        )

    add_check(
        "total_validation",
        total_valid,
        "Subtotal plus tax matches total."
        if total_valid
        else "Subtotal plus tax does not match total."
    )

    tax_components = [invoice_data.get(name) for name in ("cgst", "sgst", "igst")]
    present_tax_components = [value for value in tax_components if value is not None]
    if present_tax_components:
        parsed_components = [to_decimal(value) for value in present_tax_components]
        components_valid = (
            len(parsed_components) == len(present_tax_components)
            and all(value is not None for value in parsed_components)
            and tax_amount is not None
            and abs(sum(parsed_components, Decimal("0")) - tax_amount)
            <= Decimal("0.01")
        )
        if not components_valid:
            errors.append("Tax components do not reconcile with tax_amount.")
        add_check(
            "tax_components", components_valid,
            "Tax components match tax_amount."
            if components_valid else "Tax components require review."
        )

    # 7. Final validation status
    if errors or warnings:
        status = "NEEDS_REVIEW"
    else:
        status = "APPROVED"

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": checks
    }
