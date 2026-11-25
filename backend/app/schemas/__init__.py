from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str | None = None
    quantity: Any | None = None
    unit_price: Any | None = None
    amount: Any | None = None


class InvoiceData(BaseModel):
    model_config = ConfigDict(extra="allow")
    supplier_name: str | None = None
    supplier_gstin: str | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    currency: str | None = None
    subtotal: Any | None = None
    tax_amount: Any | None = None
    cgst: Any | None = None
    sgst: Any | None = None
    igst: Any | None = None
    total_amount: Any | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)


class ValidationCheck(BaseModel):
    check: str
    status: str
    message: str


class InvoiceValidation(BaseModel):
    status: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[ValidationCheck] = Field(default_factory=list)


class DuplicateDetection(BaseModel):
    status: str
    is_duplicate: bool
    message: str
    existing_invoice: dict[str, Any] | None = None


class InvoiceUploadResponse(BaseModel):
    status: str
    invoice_id: str
    review_status: str = "PENDING"
    filename: str | None
    raw_text: str
    cleaned_text: str
    invoice_data: InvoiceData
    validation: InvoiceValidation
    duplicate_detection: DuplicateDetection
    processing_decision: str


class InvoiceSummary(BaseModel):
    id: str
    filename: str | None = None
    invoice_data: InvoiceData
    validation: InvoiceValidation | None = None
    duplicate_detection: DuplicateDetection | None = None
    processing_decision: str
    review_status: str = "PENDING"
    rejection_reason: str | None = None
    created_at: str | None = None


class InvoiceListResponse(BaseModel):
    status: str = "success"
    total: int
    data: list[InvoiceSummary] = Field(default_factory=list)


class InvoiceDetailResponse(InvoiceSummary):
    raw_text: str | None = None
    cleaned_text: str | None = None


class InvoiceDetailEnvelope(BaseModel):
    status: str = "success"
    data: InvoiceDetailResponse


class InvoiceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    line_items: list[InvoiceLineItem] | None = None


class InvoiceRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None
