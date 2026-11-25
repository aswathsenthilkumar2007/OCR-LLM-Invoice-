from pathlib import Path
import sqlite3

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.app.schemas import (
    InvoiceDetailEnvelope,
    InvoiceListResponse,
    InvoiceRejectRequest,
    InvoiceUpdateRequest,
    InvoiceUploadResponse,
)
from backend.app.services.duplicate_detection_service import (
    approve_invoice_document,
    find_duplicate_invoice,
    get_invoice_document,
    list_invoice_documents,
    reject_invoice_document,
    save_invoice_document,
    update_invoice_document,
)
from backend.app.services.invoice_extraction_service import (
    extract_invoice_data,
    preprocess_invoice_text,
)
from backend.app.services.invoice_validation_service import (
    to_decimal,
    validate_date,
    validate_invoice_data,
)
from backend.app.services.ocr_service import extract_text_from_image, extract_text_from_pdf


router = APIRouter(prefix="/invoice", tags=["Invoice Processing"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg"}
PDF_TYPE = "application/pdf"


@router.post("/upload", response_model=InvoiceUploadResponse)
async def upload_invoice(file: UploadFile = File(...)):
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    allowed = content_type in IMAGE_TYPES | {PDF_TYPE} and suffix in {
        ".pdf", ".jpg", ".jpeg", ".png"
    }
    if not allowed:
        await file.close()
        raise HTTPException(status_code=415, detail="Supported uploads are PDF, JPG, JPEG, and PNG")
    if (content_type == PDF_TYPE) != (suffix == ".pdf"):
        await file.close()
        raise HTTPException(status_code=415, detail="File extension and content type do not match")
    if (content_type == "image/png" and suffix != ".png") or (
        content_type == "image/jpeg" and suffix not in {".jpg", ".jpeg"}
    ):
        await file.close()
        raise HTTPException(status_code=415, detail="File extension and content type do not match")

    try:
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 15 MiB upload limit")

        if content_type == PDF_TYPE:
            if b"%PDF-" not in file_bytes[:1024]:
                raise HTTPException(status_code=422, detail="File is not a valid PDF")
            ocr_result = extract_text_from_pdf(file_bytes)
        else:
            ocr_result = extract_text_from_image(file_bytes)

        raw_text = ocr_result["extracted_text"]
        cleaned_text = preprocess_invoice_text(raw_text)
        invoice_data = extract_invoice_data(cleaned_text)
        validation_result = validate_invoice_data(invoice_data)
        # Upload checks the confirmed registry but waits for explicit approval
        # before it registers a new duplicate key.
        duplicate_result = find_duplicate_invoice(invoice_data)

        if duplicate_result["is_duplicate"]:
            decision = "DUPLICATE"
        elif duplicate_result["status"] == "NOT_CHECKED" or validation_result["status"] != "APPROVED":
            decision = "NEEDS_REVIEW"
        else:
            decision = "PENDING"

        invoice_id = save_invoice_document(
            file.filename, invoice_data, validation_result, duplicate_result,
            decision, raw_text, cleaned_text,
        )
        return {
            "status": "success", "invoice_id": str(invoice_id),
            "review_status": decision if decision != "DUPLICATE" else "NEEDS_REVIEW",
            "filename": file.filename, "raw_text": raw_text,
            "cleaned_text": cleaned_text, "invoice_data": invoice_data,
            "validation": validation_result,
            "duplicate_detection": duplicate_result,
            "processing_decision": decision,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid exposing API keys or implementation details in HTTP errors.
        raise HTTPException(status_code=500, detail="Invoice processing failed") from exc
    finally:
        await file.close()


@router.patch("/{invoice_id}", response_model=InvoiceDetailEnvelope)
def edit_invoice(invoice_id: str, payload: InvoiceUpdateRequest):
    updates = payload.model_dump(mode="json", exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="At least one invoice field must be provided")

    for field in ("supplier_name", "invoice_number"):
        value = updates.get(field)
        if isinstance(value, str) and not value.strip():
            raise HTTPException(status_code=422, detail=f"{field} cannot be blank")
    for field in ("invoice_date", "due_date"):
        value = updates.get(field)
        if value is not None and not validate_date(value):
            raise HTTPException(
                status_code=422,
                detail=f"{field} must be a valid, unambiguous date (YYYY-MM-DD recommended)",
            )
    for field in ("subtotal", "tax_amount", "total_amount"):
        value = updates.get(field)
        if value is not None and to_decimal(value) is None:
            raise HTTPException(status_code=422, detail=f"{field} must be a finite monetary value")

    try:
        result = update_invoice_document(invoice_id, updates)
    except sqlite3.DatabaseError as exc:
        raise HTTPException(status_code=500, detail="Invoice update failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invoice update failed") from exc

    if result["status"] == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Invoice not found")
    if result["status"] == "APPROVED_KEY_CHANGE":
        raise HTTPException(
            status_code=409,
            detail="Supplier and invoice number cannot be changed after approval",
        )
    if result["status"] == "INVALID_APPROVED_EDIT":
        raise HTTPException(status_code=422, detail={
            "message": "Edited values would invalidate this approved invoice",
            "validation": result["validation"],
        })
    if result["status"] == "REJECTED":
        raise HTTPException(status_code=409, detail="Rejected invoices cannot be edited")
    if result["status"] == "REGISTRY_MISSING":
        raise HTTPException(status_code=409, detail="Approved invoice registry entry is missing")
    return {"status": "success", "data": result["invoice"]}


@router.post("/{invoice_id}/approve", response_model=InvoiceDetailEnvelope)
def approve_invoice(invoice_id: str):
    try:
        result = approve_invoice_document(invoice_id)
    except sqlite3.DatabaseError as exc:
        raise HTTPException(status_code=500, detail="Invoice approval failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invoice approval failed") from exc

    if result["status"] == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Invoice not found")
    if result["status"] == "INVALID":
        raise HTTPException(status_code=422, detail={
            "message": "Invoice does not meet approval requirements",
            "validation": result["validation"],
        })
    if result["status"] == "DUPLICATE":
        raise HTTPException(status_code=409, detail={
            "message": "A confirmed invoice already uses this supplier and invoice number",
            "duplicate_detection": result["duplicate_detection"],
        })
    if result["status"] == "REJECTED":
        raise HTTPException(status_code=409, detail="Rejected invoices cannot be approved")
    return {"status": "success", "data": result["invoice"]}


@router.post("/{invoice_id}/reject", response_model=InvoiceDetailEnvelope)
def reject_invoice(invoice_id: str, payload: InvoiceRejectRequest | None = None):
    reason = payload.reason.strip() if payload and payload.reason else None
    if reason and len(reason) > 1000:
        raise HTTPException(status_code=422, detail="Rejection reason cannot exceed 1000 characters")
    try:
        result = reject_invoice_document(invoice_id, reason)
    except sqlite3.DatabaseError as exc:
        raise HTTPException(status_code=500, detail="Invoice rejection failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invoice rejection failed") from exc

    if result["status"] == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Invoice not found")
    if result["status"] == "ALREADY_APPROVED":
        raise HTTPException(status_code=409, detail="Approved invoices cannot be rejected")
    return {"status": "success", "data": result["invoice"]}


@router.get("", response_model=InvoiceListResponse)
def list_invoices(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = list_invoice_documents(limit=limit, offset=offset)
    return {"status": "success", "total": total, "data": items}


@router.get("/{invoice_id}", response_model=InvoiceDetailEnvelope)
def invoice_details(invoice_id: str):
    item = get_invoice_document(invoice_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"status": "success", "data": item}
