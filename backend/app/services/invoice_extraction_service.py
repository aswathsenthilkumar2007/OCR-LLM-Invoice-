
import re
import os
import json
import math
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError


load_dotenv()


# =====================================================
# GEMINI CONFIGURATION
# =====================================================

PRIMARY_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

MAX_RETRIES = 3

RETRYABLE_ERRORS = [429, 500, 502, 503, 504]


# =====================================================
# OCR TEXT PREPROCESSING
# =====================================================

def preprocess_invoice_text(raw_text: str) -> str:
    """
    Clean and normalize OCR text.

    Preserve line breaks because they provide
    important invoice table context.
    """

    if not raw_text or not raw_text.strip():
        raise ValueError("OCR text is empty")

    text = raw_text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Normalize spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =====================================================
# GEMINI EXTRACTION PROMPT
# =====================================================

def build_extraction_prompt(cleaned_text: str) -> str:
    """
    Build a detailed prompt for accurate
    invoice information extraction.
    """

    return f"""
You are an expert invoice data extraction system.

Extract structured information from the OCR text
obtained from an invoice.

OCR text may contain:
- Spelling mistakes
- Missing characters
- Incorrect digits
- Merged words
- Misplaced decimal points
- Incorrectly recognized table columns

Use the surrounding invoice context to interpret
the information accurately.

Return ONLY valid JSON using this exact structure:

{{
    "supplier_name": null,
    "supplier_gstin": null,
    "invoice_number": null,
    "po_number": null,
    "invoice_date": null,
    "due_date": null,
    "buyer_name": null,
    "buyer_gstin": null,
    "currency": null,
    "subtotal": null,
    "tax_amount": null,
    "cgst": null,
    "sgst": null,
    "igst": null,
    "total_amount": null,
    "line_items": [
        {{
            "description": null,
            "quantity": null,
            "unit_price": null,
            "amount": null
        }}
    ]
}}

GENERAL EXTRACTION RULES:

1. Extract only information supported by the invoice.
2. Never invent missing information.
3. Use null for missing or unreadable values.
4. Return numeric values as JSON numbers.
5. Preserve all identifiable line items.
6. Return an empty array if no line items exist.
7. Extract the purchase order (PO) number separately; use null if absent.
8. Do not confuse invoice number with PO number.
9. Distinguish subtotal, tax and final total.
10. Return monetary values as decimal numbers without currency symbols.

DATE EXTRACTION RULES:

1. Identify invoice date and due date separately.
2. Examine other dates to understand the date format.
3. Return dates as YYYY-MM-DD when unambiguous.
4. Example: 26/02/2019 becomes 2019-02-26.
5. Correct obvious OCR character errors only when
   strongly supported by the surrounding evidence.
6. If a numeric date could mean either month/day or day/month, return null.
7. Never interchange invoice date and due date.

LINE ITEM EXTRACTION RULES:

1. Identify invoice table headers.
2. Understand the columns:
   Description, Quantity, Unit Price and Amount.
3. Associate values with their correct rows.
4. Do not confuse quantity with unit price.
5. Do not confuse unit price with total amount.
6. Preserve decimal values accurately.
7. Read descriptions using nearby OCR context.
8. Do not merge separate line items.
9. Extract all identifiable line items.

FINANCIAL VALIDATION RULES:

1. Check quantity multiplied by unit price.
2. Compare the result with the line-item amount.
3. Compare the sum of line items with the subtotal.
4. Compare subtotal plus tax with the total.
5. Use arithmetic as supporting evidence.
6. Do not silently invent or replace printed amounts.
7. If an amount cannot be resolved reliably, return null.

EXAMPLE:

OCR:

1 Product A 100.00 100.00
2 Product B 15.00 30.00
3 Labor 3hrs 5.00 1.00

Printed subtotal: 145.00

The third item's expected arithmetic is:

3 x 5.00 = 15.00

However, OCR reads 1.00.

Do not automatically assume 15.00 was printed.
Use the subtotal and row context as evidence.
If the correction is not sufficiently reliable,
return null for the unresolved amount.

OUTPUT RULES:

1. Return valid JSON only.
2. No Markdown.
3. No explanations outside JSON.
4. Do not add additional fields.
5. Use null instead of guessing.
6. Use double quotes for JSON keys and strings.

OCR TEXT:

{cleaned_text}
"""


# =====================================================
# GEMINI MODEL WITH AUTOMATIC FALLBACK
# =====================================================

def generate_with_fallback(client, prompt: str) -> str:
    """
    Try the primary Gemini model first.

    If temporary API errors persist,
    switch to the fallback model.
    """

    models = [
        PRIMARY_MODEL,
        FALLBACK_MODEL
    ]

    for model in models:

        for attempt in range(MAX_RETRIES):

            try:

                print(
                    f"Gemini request: {model} | "
                    f"Attempt {attempt + 1}/{MAX_RETRIES}"
                )

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )

                if not response.text:
                    raise ValueError(
                        "Gemini returned an empty response"
                    )

                print(
                    f"Gemini extraction successful using {model}"
                )

                return response.text

            except APIError as e:

                error_code = getattr(e, "code", None)

                # Do not retry permanent API errors
                if error_code not in RETRYABLE_ERRORS:

                    raise RuntimeError(
                        f"Gemini API error ({error_code}): {e}"
                    ) from e

                # Move to fallback after final retry
                if attempt == MAX_RETRIES - 1:

                    print(
                        f"{model} unavailable after "
                        f"{MAX_RETRIES} attempts."
                    )

                    break

                wait_time = min(
                    2 ** (attempt + 1),
                    30
                )

                print(
                    f"Temporary error {error_code}. "
                    f"Retrying in {wait_time} seconds..."
                )

                time.sleep(wait_time)

    raise RuntimeError(
        "All configured Gemini models are unavailable. "
        "Please try again later."
    )


# =====================================================
# JSON RESPONSE VALIDATION
# =====================================================

def validate_invoice_response(invoice_data: dict) -> dict:
    """
    Validate Gemini's structured JSON response.
    """

    if not isinstance(invoice_data, dict):
        raise ValueError(
            "Gemini response must be a JSON object"
        )

    required_invoice_fields = [
        "supplier_name",
        "supplier_gstin",
        "invoice_number",
        "po_number",
        "invoice_date",
        "due_date",
        "buyer_name",
        "buyer_gstin",
        "currency",
        "subtotal",
        "tax_amount",
        "cgst",
        "sgst",
        "igst",
        "total_amount",
        "line_items"
    ]

    for field in required_invoice_fields:

        if field not in invoice_data:

            raise ValueError(
                f"Missing invoice field: {field}"
            )

    line_items = invoice_data["line_items"]

    if not isinstance(line_items, list):

        raise ValueError(
            "Gemini response contains invalid line_items"
        )

    required_item_fields = {
        "description",
        "quantity",
        "unit_price",
        "amount"
    }

    for index, item in enumerate(line_items):

        if not isinstance(item, dict):

            raise ValueError(
                f"Invalid line item at index {index}"
            )

        missing_fields = (
            required_item_fields - set(item.keys())
        )

        if missing_fields:

            raise ValueError(
                f"Line item {index + 1} missing fields: "
                f"{missing_fields}"
            )

        for field in ("quantity", "unit_price", "amount"):
            value = item.get(field)
            if isinstance(value, float) and not math.isfinite(value):
                item[field] = None

    for field in (
        "subtotal", "tax_amount", "cgst", "sgst", "igst", "total_amount"
    ):
        value = invoice_data.get(field)
        if isinstance(value, float) and not math.isfinite(value):
            invoice_data[field] = None

    return invoice_data


# =====================================================
# MAIN INVOICE EXTRACTION FUNCTION
# =====================================================

def extract_invoice_data(cleaned_text: str) -> dict:
    """
    Extract structured invoice information using Gemini.

    Features:
    - Context-aware extraction
    - Date normalization instructions
    - Improved line-item interpretation
    - Financial consistency instructions
    - Automatic retry
    - Primary and fallback models
    - JSON validation
    """

    if not cleaned_text or not cleaned_text.strip():

        raise ValueError(
            "Cleaned invoice text is empty"
        )

    # Load Gemini API key
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    # Initialize Gemini client
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=60000
        )
    )

    # Build extraction prompt
    prompt = build_extraction_prompt(cleaned_text)

    # Generate response with model fallback
    response_text = generate_with_fallback(
        client,
        prompt
    )

    # Parse JSON response
    try:

        invoice_data = json.loads(response_text)

    except json.JSONDecodeError as e:

        raise ValueError(
            f"Gemini returned invalid JSON: {str(e)}"
        ) from e

    # Validate response structure
    invoice_data = validate_invoice_response(
        invoice_data
    )

    print(
        "Gemini invoice extraction and validation completed."
    )

    return invoice_data
