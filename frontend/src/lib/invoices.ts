import type { ApiInvoice, ApiLineItem } from "./api";

export type InvoiceStatus = "PENDING" | "NEEDS_REVIEW" | "APPROVED" | "REJECTED" | "DUPLICATE";

export type Invoice = {
  id: string;
  number: string;
  vendor: string;
  date: string;
  amount: number;
  currency: string;
  validationStatus: string;
  status: InvoiceStatus;
  poNumber?: string | null;
  dueDate?: string | null;
  filename?: string | null;
  rejectionReason?: string | null;
  validationErrors: string[];
  lineItems: ApiLineItem[];
  raw?: ApiInvoice;
};

export function normalizeStatus(invoice: ApiInvoice): InvoiceStatus {
  const value = (invoice.processing_decision || invoice.review_status || "PENDING").toUpperCase();
  if (value === "DUPLICATE") return "DUPLICATE";
  if (value === "APPROVED") return "APPROVED";
  if (value === "REJECTED") return "REJECTED";
  if (value === "NEEDS_REVIEW") return "NEEDS_REVIEW";
  return "PENDING";
}

export function mapInvoice(item: ApiInvoice): Invoice {
  const data = item.invoice_data || {};
  return {
    id: item.id,
    number: data.invoice_number || "Invoice pending",
    vendor: data.supplier_name || "Unknown vendor",
    date: data.invoice_date || item.created_at || "—",
    amount: Number(data.total_amount) || 0,
    currency: data.currency || "USD",
    validationStatus: item.validation?.status || (normalizeStatus(item) === "NEEDS_REVIEW" ? "NEEDS_REVIEW" : "VALID"),
    status: normalizeStatus(item),
    poNumber: data.po_number,
    dueDate: data.due_date,
    filename: item.filename,
    rejectionReason: item.rejection_reason,
    validationErrors: item.validation?.errors || [],
    lineItems: data.line_items || [],
    raw: item,
  };
}

export const demoInvoices: Invoice[] = [
  {
    id: "demo-1001", number: "INV-2026-0842", vendor: "Northstar Office Supply", date: "2026-11-24", amount: 12840.5, currency: "USD", validationStatus: "VALID", status: "PENDING", poNumber: "PO-24018", dueDate: "2026-12-24", filename: "northstar_0842.pdf", validationErrors: [], lineItems: [{ description: "Workplace equipment", quantity: 5, unit_price: 2100, amount: 10500 }, { description: "Delivery and handling", quantity: 1, unit_price: 2340.5, amount: 2340.5 }],
  },
  {
    id: "demo-1002", number: "INV-2026-0839", vendor: "Meridian Cloud Services", date: "2026-11-23", amount: 6420, currency: "USD", validationStatus: "VALID", status: "APPROVED", poNumber: "PO-23972", dueDate: "2026-12-23", filename: "meridian_nov.pdf", validationErrors: [], lineItems: [{ description: "Cloud platform — November", quantity: 1, unit_price: 6000, amount: 6000 }, { description: "Premium support", quantity: 1, unit_price: 420, amount: 420 }],
  },
  {
    id: "demo-1003", number: "INV-58321", vendor: "Acme Industrial Parts", date: "2026-11-22", amount: 3890.75, currency: "USD", validationStatus: "NEEDS_REVIEW", status: "NEEDS_REVIEW", poNumber: "PO-23911", dueDate: "2026-12-22", filename: "acme_58321.png", validationErrors: ["Invoice date needs confirmation."], lineItems: [{ description: "Replacement assemblies", quantity: 7, unit_price: 500, amount: 3500 }, { description: "Freight", quantity: 1, unit_price: 390.75, amount: 390.75 }],
  },
  {
    id: "demo-1004", number: "BILL-9918", vendor: "Atelier Design Studio", date: "2026-11-21", amount: 2150, currency: "USD", validationStatus: "VALID", status: "APPROVED", poNumber: "PO-23880", dueDate: "2026-12-21", filename: "atelier_9918.jpg", validationErrors: [], lineItems: [{ description: "Brand design services", quantity: 10, unit_price: 215, amount: 2150 }],
  },
  {
    id: "demo-1005", number: "INV-2026-0811", vendor: "Brightline Logistics", date: "2026-11-20", amount: 987.2, currency: "USD", validationStatus: "VALID", status: "REJECTED", poNumber: "PO-23795", dueDate: "2026-12-20", filename: "brightline_0811.pdf", rejectionReason: "Purchase order reference could not be verified.", validationErrors: [], lineItems: [{ description: "Regional freight service", quantity: 1, unit_price: 987.2, amount: 987.2 }],
  },
  {
    id: "demo-1006", number: "INV-2026-0794", vendor: "Northstar Office Supply", date: "2026-11-18", amount: 12840.5, currency: "USD", validationStatus: "VALID", status: "DUPLICATE", poNumber: "PO-23682", dueDate: "2026-12-18", filename: "northstar_0794.pdf", validationErrors: [], lineItems: [{ description: "Workplace equipment", quantity: 5, unit_price: 2100, amount: 10500 }],
  },
];

