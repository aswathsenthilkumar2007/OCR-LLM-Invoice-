export type ApiLineItem = {
  description?: string | null;
  quantity?: number | string | null;
  unit_price?: number | string | null;
  amount?: number | string | null;
};

export type ApiInvoice = {
  id: string;
  filename?: string | null;
  invoice_data: {
    supplier_name?: string | null;
    invoice_number?: string | null;
    invoice_date?: string | null;
    due_date?: string | null;
    currency?: string | null;
    subtotal?: number | string | null;
    tax_amount?: number | string | null;
    total_amount?: number | string | null;
    po_number?: string | null;
    buyer_name?: string | null;
    line_items?: ApiLineItem[];
  };
  validation?: { status?: string; errors?: string[]; warnings?: string[] } | null;
  duplicate_detection?: { status?: string; is_duplicate?: boolean; message?: string } | null;
  processing_decision: string;
  review_status?: string;
  rejection_reason?: string | null;
  created_at?: string | null;
  raw_text?: string | null;
};

export type ApiInvoiceList = { status: string; total: number; data: ApiInvoice[] };

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "The request could not be completed.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function fetchInvoices(): Promise<ApiInvoiceList> {
  return apiRequest<ApiInvoiceList>("/invoice?limit=100&offset=0");
}

export async function uploadInvoice(file: File): Promise<ApiInvoice> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiRequest<{ invoice_id: string; invoice_data: ApiInvoice["invoice_data"]; validation: ApiInvoice["validation"]; duplicate_detection: ApiInvoice["duplicate_detection"]; processing_decision: string; review_status: string; filename: string }>("/invoice/upload", { method: "POST", body: form });
  return {
    id: response.invoice_id,
    filename: response.filename,
    invoice_data: response.invoice_data,
    validation: response.validation,
    duplicate_detection: response.duplicate_detection,
    processing_decision: response.processing_decision,
    review_status: response.review_status,
  };
}

export async function approveInvoice(id: string): Promise<ApiInvoice> {
  const result = await apiRequest<{ data: ApiInvoice }>(`/invoice/${encodeURIComponent(id)}/approve`, { method: "POST" });
  return result.data;
}

export async function rejectInvoice(id: string, reason?: string): Promise<ApiInvoice> {
  const result = await apiRequest<{ data: ApiInvoice }>(`/invoice/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  return result.data;
}

export async function updateInvoice(id: string, update: Record<string, unknown>): Promise<ApiInvoice> {
  const result = await apiRequest<{ data: ApiInvoice }>(`/invoice/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  return result.data;
}
