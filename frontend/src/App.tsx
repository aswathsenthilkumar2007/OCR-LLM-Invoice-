import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Bell, Check, ChevronDown,
  ChevronLeft, ChevronRight, CircleAlert, Clock3, CloudUpload, Copy, FileCheck2,
  FileClock, FilePlus2, FileSearch, Files, Filter, LayoutDashboard, LifeBuoy, Menu,
  MoreHorizontal, Search, Settings2, ShieldCheck, Sparkles, Upload, WalletCards, X,
  XCircle, BarChart3, FileWarning, type LucideIcon,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { approveInvoice, fetchInvoices, rejectInvoice, updateInvoice, uploadInvoice } from "./lib/api";
import { demoInvoices, mapInvoice, type Invoice } from "./lib/invoices";
import { Button, Card, IconButton, StatusBadge } from "./components/ui";
import "./styles.css";

type View = "Overview" | "All Invoices" | "Pending Reviews" | "Approved Invoices" | "Rejected Invoices" | "Duplicate Invoices" | "Reports & Analytics" | "Settings";

const navigation: { label: View | "Upload Invoice"; icon: LucideIcon; section?: string }[] = [
  { label: "Overview", icon: LayoutDashboard, section: "WORKSPACE" },
  { label: "Upload Invoice", icon: FilePlus2 },
  { label: "All Invoices", icon: Files, section: "INVOICES" },
  { label: "Pending Reviews", icon: FileClock },
  { label: "Approved Invoices", icon: FileCheck2 },
  { label: "Rejected Invoices", icon: XCircle },
  { label: "Duplicate Invoices", icon: Copy },
  { label: "Reports & Analytics", icon: BarChart3, section: "INSIGHTS" },
  { label: "Settings", icon: Settings2, section: "PREFERENCES" },
];

const monthlyActivity = [
  { month: "Jun", approved: 108, pending: 24, rejected: 8 },
  { month: "Jul", approved: 124, pending: 28, rejected: 11 },
  { month: "Aug", approved: 116, pending: 22, rejected: 7 },
  { month: "Sep", approved: 145, pending: 31, rejected: 10 },
  { month: "Oct", approved: 158, pending: 26, rejected: 12 },
  { month: "Nov", approved: 172, pending: 34, rejected: 9 },
];

const trendData = [
  { month: "Jun", value: 76 }, { month: "Jul", value: 82 }, { month: "Aug", value: 79 },
  { month: "Sep", value: 88 }, { month: "Oct", value: 91 }, { month: "Nov", value: 94 },
];

const initials = (name: string) => name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
const titleCase = (value: string) => value.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

function formatMoney(value: number, currency = "USD") {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: /^[A-Z]{3}$/.test(currency) ? currency : "USD", maximumFractionDigits: 2 }).format(value);
  } catch {
    return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

function formatDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", year: "numeric" }).format(date);
}

function statusTone(status: string) {
  const normalized = status.toUpperCase();
  if (normalized === "APPROVED" || normalized === "VALID") return "green";
  if (normalized === "REJECTED" || normalized === "INVALID") return "red";
  if (normalized === "DUPLICATE") return "purple";
  if (normalized === "NEEDS_REVIEW" || normalized === "PENDING") return "amber";
  return "slate";
}

function NavItem({ label, icon: Icon, active, count, compact, onClick }: {
  label: string; icon: LucideIcon; active: boolean; count?: number; compact?: boolean; onClick: () => void;
}) {
  return (
    <button className={`nav-item ${active ? "nav-item-active" : ""} ${compact ? "nav-item-compact" : ""}`} onClick={onClick} title={compact ? label : undefined}>
      <Icon size={18} strokeWidth={1.8} />
      {!compact && <><span className="nav-label">{label}</span>{count !== undefined && <span className="nav-count">{count}</span>}</>}
    </button>
  );
}

function StatCard({ title, value, change, note, icon: Icon, tone, trend = "up" }: {
  title: string; value: string; change: string; note: string; icon: LucideIcon; tone: string; trend?: "up" | "down";
}) {
  return (
    <Card className="stat-card">
      <div className="stat-card-top">
        <div className={`stat-icon stat-icon-${tone}`}><Icon size={19} strokeWidth={1.8} /></div>
        <button className="stat-more" aria-label={`More about ${title}`}><MoreHorizontal size={18} /></button>
      </div>
      <p className="stat-title">{title}</p>
      <div className="stat-value-row"><strong>{value}</strong><span className={`stat-change ${trend === "down" ? "stat-change-down" : ""}`}>{trend === "down" ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />}{change}</span></div>
      <p className="stat-note">{note}</p>
    </Card>
  );
}

function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  return <span className={`avatar ${small ? "avatar-small" : ""}`}>{initials(name)}</span>;
}

function InvoiceDrawer({ invoice, onClose, onChanged, onMessage }: {
  invoice: Invoice; onClose: () => void; onChanged: (invoice: Invoice) => void; onMessage: (message: string, kind?: "success" | "error") => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [fields, setFields] = useState({ vendor: invoice.vendor, number: invoice.number, date: invoice.date, amount: String(invoice.amount), currency: invoice.currency });
  const needsDecision = invoice.status === "PENDING" || invoice.status === "NEEDS_REVIEW";

  useEffect(() => {
    setFields({ vendor: invoice.vendor, number: invoice.number, date: invoice.date, amount: String(invoice.amount), currency: invoice.currency });
    setEditing(false);
  }, [invoice.id]);

  async function save() {
    setBusy(true);
    try {
      let updated: Invoice;
      if (invoice.id.startsWith("demo-")) {
        updated = { ...invoice, vendor: fields.vendor, number: fields.number, date: fields.date, amount: Number(fields.amount), currency: fields.currency };
      } else {
        const raw = await updateInvoice(invoice.id, { supplier_name: fields.vendor, invoice_number: fields.number, invoice_date: fields.date, total_amount: fields.amount, currency: fields.currency });
        updated = mapInvoice(raw);
      }
      onChanged(updated);
      setEditing(false);
      onMessage("Invoice changes saved.");
    } catch (error) {
      onMessage(error instanceof Error ? error.message : "Unable to save invoice changes.", "error");
    } finally { setBusy(false); }
  }

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    try {
      let updated: Invoice;
      if (invoice.id.startsWith("demo-")) {
        updated = { ...invoice, status: decision === "approve" ? "APPROVED" : "REJECTED", validationStatus: decision === "approve" ? "APPROVED" : invoice.validationStatus, rejectionReason: decision === "reject" ? (reason || "Rejected from dashboard") : null };
      } else {
        updated = mapInvoice(decision === "approve" ? await approveInvoice(invoice.id) : await rejectInvoice(invoice.id, reason));
      }
      onChanged(updated);
      onMessage(decision === "approve" ? "Invoice approved and registered." : "Invoice rejected.");
      onClose();
    } catch (error) {
      onMessage(error instanceof Error ? error.message : `Unable to ${decision} invoice.`, "error");
    } finally { setBusy(false); }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="invoice-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className="drawer-header"><div><p className="eyebrow">INVOICE DETAILS</p><h2 id="drawer-title">{invoice.number}</h2></div><IconButton label="Close details" onClick={onClose}><X size={18} /></IconButton></div>
        <div className="drawer-scroll">
          <div className="drawer-vendor-row"><Avatar name={invoice.vendor} /><div><strong>{invoice.vendor}</strong><span>{invoice.filename || "Uploaded invoice"}</span></div><StatusBadge tone={statusTone(invoice.status)}>{titleCase(invoice.status)}</StatusBadge></div>
          {invoice.validationErrors.length > 0 && <div className="validation-alert"><CircleAlert size={17} /><div><strong>Review recommended</strong><span>{invoice.validationErrors.join(" ")}</span></div></div>}
          <div className="drawer-section-heading"><h3>Invoice information</h3>{needsDecision && <button className="text-button" onClick={() => setEditing((value) => !value)}>{editing ? "Cancel" : "Edit details"}</button>}</div>
          <div className="detail-grid">
            <DetailField label="Vendor name" value={fields.vendor} editing={editing} onChange={(value) => setFields({ ...fields, vendor: value })} />
            <DetailField label="Invoice number" value={fields.number} editing={editing} onChange={(value) => setFields({ ...fields, number: value })} />
            <DetailField label="Invoice date" value={fields.date} editing={editing} onChange={(value) => setFields({ ...fields, date: value })} />
            <DetailField label="Due date" value={invoice.dueDate || "â€”"} />
            <DetailField label="PO number" value={invoice.poNumber || "â€”"} />
            <DetailField label="Currency" value={fields.currency} editing={editing} onChange={(value) => setFields({ ...fields, currency: value.toUpperCase() })} />
            <DetailField label="Total amount" value={formatMoney(Number(fields.amount), fields.currency)} editing={editing} onChange={(value) => setFields({ ...fields, amount: value })} />
            <DetailField label="Validation" value={titleCase(invoice.validationStatus)} />
          </div>
          {editing && <Button variant="primary" className="drawer-save" disabled={busy} onClick={save}>{busy ? "Savingâ€¦" : "Save changes"}</Button>}
          <div className="drawer-section-heading line-heading"><h3>Line items</h3><span>{invoice.lineItems.length} items</span></div>
          <div className="line-items-card">
            {invoice.lineItems.length ? invoice.lineItems.map((item, index) => <div className="line-item-row" key={`${item.description}-${index}`}><div><strong>{item.description || "Line item"}</strong><span>{item.quantity ?? "â€”"} Ã— {formatMoney(Number(item.unit_price) || 0, invoice.currency)}</span></div><b>{formatMoney(Number(item.amount) || 0, invoice.currency)}</b></div>) : <p className="empty-lines">No line items were extracted.</p>}
          </div>
          {invoice.rejectionReason && <div className="rejection-note"><strong>Rejection reason</strong><p>{invoice.rejectionReason}</p></div>}
          {needsDecision && <div className="drawer-decision"><label htmlFor="reject-reason">Rejection note <span>Optional</span></label><textarea id="reject-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Add context for the requesterâ€¦" rows={3} /><div className="drawer-actions"><Button variant="secondary" disabled={busy} onClick={() => decide("reject")}><XCircle size={16} /> Reject</Button><Button variant="primary" disabled={busy} onClick={() => decide("approve")}><Check size={16} /> Approve invoice</Button></div></div>}
        </div>
      </aside>
    </div>
  );
}

function DetailField({ label, value, editing, onChange }: { label: string; value: string; editing?: boolean; onChange?: (value: string) => void }) {
  return <div className="detail-field"><span>{label}</span>{editing && onChange ? <input value={value} onChange={(event) => onChange(event.target.value)} aria-label={label} /> : <strong>{value}</strong>}</div>;
}

function App() {
  const [invoices, setInvoices] = useState<Invoice[]>(demoInvoices);
  const [view, setView] = useState<View>("Overview");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);
  const [toast, setToast] = useState<{ message: string; kind: "success" | "error" } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    fetchInvoices().then((response) => {
      if (alive) { setInvoices(response.data.map(mapInvoice)); setApiConnected(true); }
    }).catch(() => { if (alive) setApiConnected(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const counts = useMemo(() => ({
    total: invoices.length,
    pending: invoices.filter((item) => item.status === "PENDING" || item.status === "NEEDS_REVIEW").length,
    approved: invoices.filter((item) => item.status === "APPROVED").length,
    rejected: invoices.filter((item) => item.status === "REJECTED").length,
    duplicate: invoices.filter((item) => item.status === "DUPLICATE").length,
  }), [invoices]);

  const visibleInvoices = useMemo(() => {
    let result = invoices;
    if (view === "Pending Reviews") result = result.filter((item) => item.status === "PENDING" || item.status === "NEEDS_REVIEW");
    if (view === "Approved Invoices") result = result.filter((item) => item.status === "APPROVED");
    if (view === "Rejected Invoices") result = result.filter((item) => item.status === "REJECTED");
    if (view === "Duplicate Invoices") result = result.filter((item) => item.status === "DUPLICATE");
    const query = search.trim().toLowerCase();
    if (query) result = result.filter((item) => `${item.number} ${item.vendor} ${item.status}`.toLowerCase().includes(query));
    return result;
  }, [invoices, view, search]);

  function notify(message: string, kind: "success" | "error" = "success") { setToast({ message, kind }); }

  function updateRow(updated: Invoice) {
    setInvoices((items) => items.map((item) => item.id === updated.id ? updated : item));
    setSelected(updated);
  }

  function selectNavigation(label: string) {
    if (label === "Upload Invoice") { fileInput.current?.click(); setMenuOpen(false); return; }
    setView(label as View);
    setMenuOpen(false);
  }

  async function handleUpload(file?: File) {
    if (!file) return;
    setUploading(true);
    try {
      const uploaded = mapInvoice(await uploadInvoice(file));
      setInvoices((items) => [uploaded, ...items]);
      setApiConnected(true);
      notify("Invoice uploaded and processed successfully.");
      setSelected(uploaded);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not upload this invoice. Check the API connection.", "error");
    } finally { setUploading(false); if (fileInput.current) fileInput.current.value = ""; }
  }

  const dateLabel = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date());
  const pageTitle = view === "Overview" ? "Good morning, Alex" : view;
  const pendingReviewCount = counts.pending;

  return (
    <div className="app-shell min-h-screen text-slate-700">
      {menuOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand"><div className="brand-mark"><ScanLogo /></div><div className="brand-copy"><strong>OCR Invoice AI</strong><span>INTELLIGENT AP</span></div><button className="sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={18} /></button></div>
        <div className="workspace-switch"><span className="workspace-avatar">A</span><span className="workspace-copy"><strong>Acme Corporation</strong><small>Enterprise workspace</small></span><ChevronDown size={15} /></div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map((item, index) => {
            const previousSection = navigation[index - 1]?.section;
            return <div key={item.label}>{item.section && <p className="nav-section">{item.section}</p>}<NavItem label={item.label} icon={item.icon} active={item.label === view || (view === "Overview" && item.label === "Overview")} compact={false} count={item.label === "Pending Reviews" ? pendingReviewCount : undefined} onClick={() => selectNavigation(item.label)} />{previousSection && item.section && <span className="section-gap" />}</div>;
          })}
        </nav>
        <div className="sidebar-bottom"><div className="ai-usage"><div className="usage-icon"><Sparkles size={16} /></div><div className="usage-copy"><strong>AI processing</strong><span>82% of monthly volume</span></div><div className="usage-track"><span /></div><button onClick={() => selectNavigation("Reports & Analytics")}>View usage <ArrowRight size={13} /></button></div><button className="help-link"><LifeBuoy size={17} /><span>Help & support</span><ChevronRight size={15} /></button><div className="sidebar-profile"><Avatar name="Alex Morgan" /><div className="profile-copy"><strong>Alex Morgan</strong><span>Finance admin</span></div><MoreHorizontal size={19} /></div></div>
      </aside>

      <div className="main-column">
        <header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><span className="breadcrumb-muted">Workspace</span><ChevronRight size={14} /><span className="breadcrumb-current">{view}</span></div><div className="topbar-actions"><label className="global-search"><Search size={17} /><input aria-label="Search invoices" placeholder="Search invoices, vendors..." value={search} onChange={(event) => setSearch(event.target.value)} /><kbd>âŒ˜ K</kbd></label><span className={`connection-indicator ${apiConnected ? "connected" : "demo-mode"}`} title={apiConnected ? "Connected to invoice API" : "Showing sample dashboard data"}><span />{apiConnected ? "Connected" : "Demo data"}</span><IconButton label="Notifications" className="notification-button"><Bell size={19} /><i /></IconButton><div className="topbar-avatar"><Avatar name="Alex Morgan" small /></div></div></header>

        <main className="dashboard-main">
          <div className="page-heading"><div><div className="date-kicker"><span className="date-dot" />{dateLabel}</div><h1>{pageTitle}<span className="heading-period">.</span></h1><p>{view === "Overview" ? "Hereâ€™s whatâ€™s happening with your invoices today." : `Monitor and manage your ${view.toLowerCase()} in one place.`}</p></div><div className="heading-actions"><Button variant="secondary" className="filter-button"><Filter size={16} /> Last 30 days <ChevronDown size={14} /></Button><Button variant="primary" onClick={() => fileInput.current?.click()} disabled={uploading}><Upload size={16} />{uploading ? "Processingâ€¦" : "Upload invoice"}</Button></div></div>

          <section className="stat-grid" aria-label="Invoice overview metrics">
            <StatCard title="Total invoices" value={counts.total.toLocaleString()} change="12.8%" note="vs. previous month" icon={Files} tone="blue" />
            <StatCard title="Pending review" value={counts.pending.toLocaleString()} change="4.2%" note="Needs your attention" icon={Clock3} tone="amber" trend="down" />
            <StatCard title="Approved invoices" value={counts.approved.toLocaleString()} change="18.6%" note="vs. previous month" icon={ShieldCheck} tone="green" />
            <StatCard title="Rejected invoices" value={counts.rejected.toLocaleString()} change="2.4%" note="vs. previous month" icon={XCircle} tone="red" trend="down" />
            <StatCard title="Duplicates flagged" value={counts.duplicate.toLocaleString()} change="8.1%" note="Prevented duplicate pay" icon={Copy} tone="purple" />
          </section>

          <section className="analytics-grid" aria-label="Invoice analytics">
            <Card className="chart-card processing-card"><div className="card-heading"><div><div className="card-title-row"><h2>Invoice processing</h2><span className="live-tag"><span /> LIVE</span></div><p>Monthly volume and processing outcomes</p></div><button className="period-select">Last 6 months <ChevronDown size={14} /></button></div><div className="chart-summary"><strong>842</strong><span>invoices processed</span><span className="summary-change"><ArrowUpRight size={13} /> 14.6%</span></div><div className="processing-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={monthlyActivity} barGap={5} barCategoryGap="28%" margin={{ top: 6, right: 4, left: -20, bottom: 0 }}><CartesianGrid vertical={false} stroke="#edf0f5" strokeDasharray="4 5" /><XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fill: "#8c97aa", fontSize: 12 }} dy={10} /><YAxis tickLine={false} axisLine={false} tick={{ fill: "#a0a9b8", fontSize: 11 }} ticks={[0, 50, 100, 150, 200]} /><Tooltip cursor={{ fill: "#f5f8ff" }} contentStyle={{ border: "1px solid #e8edf4", borderRadius: 12, boxShadow: "0 8px 24px #182c4d12", fontSize: 12 }} /><Bar dataKey="approved" name="Approved" stackId="invoice" fill="#3478f6" radius={[0, 0, 4, 4]} /><Bar dataKey="pending" name="Pending" stackId="invoice" fill="#a9c7ff" /><Bar dataKey="rejected" name="Rejected" stackId="invoice" fill="#e7edf6" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div><div className="chart-legend"><span><i className="legend-blue" /> Approved</span><span><i className="legend-lightblue" /> Pending</span><span><i className="legend-gray" /> Rejected</span></div></Card>

            <Card className="status-chart-card"><div className="card-heading"><div><h2>Approval overview</h2><p>Invoice decision breakdown</p></div><IconButton label="More chart options"><MoreHorizontal size={19} /></IconButton></div><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={[{ name: "Approved", value: counts.approved || 1 }, { name: "Pending", value: counts.pending || 1 }, { name: "Rejected", value: counts.rejected || 1 }, { name: "Duplicate", value: counts.duplicate || 1 }]} dataKey="value" nameKey="name" innerRadius={69} outerRadius={91} paddingAngle={3} stroke="none" startAngle={90} endAngle={-270}><Cell fill="#3478f6" /><Cell fill="#f6bd4b" /><Cell fill="#e76c70" /><Cell fill="#9b78e8" /></Pie><Tooltip contentStyle={{ border: "1px solid #e8edf4", borderRadius: 12, fontSize: 12 }} /></PieChart></ResponsiveContainer><div className="donut-center"><strong>{counts.total}</strong><span>Total invoices</span></div></div><div className="status-legend"><div><i className="legend-blue" /><span>Approved</span><strong>{counts.approved}</strong></div><div><i className="legend-amber" /><span>Pending review</span><strong>{counts.pending}</strong></div><div><i className="legend-red" /><span>Rejected</span><strong>{counts.rejected}</strong></div><div><i className="legend-purple" /><span>Duplicates</span><strong>{counts.duplicate}</strong></div></div></Card>
          </section>

          <section className="bottom-grid">
            <Card className="invoices-card"><div className="table-heading"><div><div className="table-title-line"><h2>{view === "Overview" ? "Recent invoices" : view}</h2><span className="table-count">{visibleInvoices.length}</span></div><p>Track, review and manage your latest activity</p></div><div className="table-tools"><button className="table-filter"><Filter size={15} /> Filter</button><button className="table-view-all" onClick={() => setView("All Invoices")}>View all <ArrowRight size={14} /></button></div></div><div className="invoice-table-wrap"><table className="invoice-table"><thead><tr><th><span>INVOICE</span></th><th><span>VENDOR</span></th><th><span>INVOICE DATE</span></th><th><span>AMOUNT</span></th><th><span>VALIDATION</span></th><th><span>APPROVAL STATUS</span></th><th><span /></th></tr></thead><tbody>{visibleInvoices.slice(0, 6).map((invoice, index) => <tr key={invoice.id} onClick={() => setSelected(invoice)} className="invoice-row"><td><div className="invoice-number-cell"><span className={`file-type file-type-${index % 3}`}><Files size={15} /></span><strong>{invoice.number}</strong></div></td><td><div className="vendor-cell"><Avatar name={invoice.vendor} small /><span>{invoice.vendor}</span></div></td><td className="date-cell">{formatDate(invoice.date)}</td><td className="amount-cell">{formatMoney(invoice.amount, invoice.currency)}</td><td><StatusBadge tone={statusTone(invoice.validationStatus)}>{titleCase(invoice.validationStatus)}</StatusBadge></td><td><StatusBadge tone={statusTone(invoice.status)}>{titleCase(invoice.status)}</StatusBadge></td><td><IconButton label={`Open ${invoice.number}`} className="row-open" onClick={(event) => { event.stopPropagation(); setSelected(invoice); }}><MoreHorizontal size={18} /></IconButton></td></tr>)}</tbody></table>{visibleInvoices.length === 0 && <div className="empty-state"><FileSearch size={24} /><strong>No invoices found</strong><span>Try changing your search or current filter.</span></div>}</div><div className="table-footer"><span>Showing <strong>{Math.min(visibleInvoices.length, 6)}</strong> of <strong>{visibleInvoices.length}</strong> invoices</span><div className="pagination"><button disabled aria-label="Previous page"><ChevronLeft size={15} /></button><button className="page-current">1</button><button disabled>2</button><button disabled>3</button><span>â€¦</span><button disabled>Next</button><button disabled aria-label="Next page"><ChevronRight size={15} /></button></div></div></Card>

            <div className="right-rail"><Card className="quick-actions-card"><div className="quick-heading"><div><h2>Quick actions</h2><p>Move work forward faster</p></div><div className="quick-heading-icon"><Sparkles size={16} /></div></div><button className="quick-action upload-action" onClick={() => fileInput.current?.click()}><span className="quick-action-icon blue-action"><CloudUpload size={18} /></span><span><strong>Upload new invoice</strong><small>PDF, JPG or PNG Â· up to 15 MB</small></span><ArrowRight size={16} /></button><button className="quick-action" onClick={() => setView("Pending Reviews")}><span className="quick-action-icon amber-action"><FileWarning size={18} /></span><span><strong>Review pending</strong><small>{counts.pending} invoices are waiting</small></span><ArrowRight size={16} /></button><button className="quick-action" onClick={() => setView("Reports & Analytics")}><span className="quick-action-icon violet-action"><BarChart3 size={18} /></span><span><strong>View reports</strong><small>Insights and spend trends</small></span><ArrowRight size={16} /></button></Card>
              <Card className="efficiency-card"><div className="efficiency-heading"><span className="efficiency-icon"><Activity size={17} /></span><span className="efficiency-period">THIS MONTH</span></div><div className="efficiency-value"><strong>94.2%</strong><span><ArrowUpRight size={13} /> 3.8%</span></div><p>Automation efficiency</p><div className="efficiency-sparkline"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trendData} margin={{ top: 2, right: 1, left: 1, bottom: 0 }}><defs><linearGradient id="efficiencyFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3478f6" stopOpacity={0.16} /><stop offset="95%" stopColor="#3478f6" stopOpacity={0} /></linearGradient></defs><Area type="monotone" dataKey="value" stroke="#3478f6" strokeWidth={2.4} fill="url(#efficiencyFill)" /></AreaChart></ResponsiveContainer></div><div className="efficiency-foot"><span><span className="small-green-dot" /> 7.4% above target</span><span>Target 86.8%</span></div></Card>
              <div className="help-card"><div className="help-card-art"><WalletCards size={26} /><span /><i /></div><div><strong>Need a hand?</strong><p>Explore our guide to smarter invoice workflows.</p><button onClick={() => notify("Help center is coming soon.")}>Explore help center <ArrowRight size={13} /></button></div></div>
            </div>
          </section>

          <footer className="dashboard-footer"><span>Â© 2026 OCR Invoice AI</span><span><i /> All systems operational</span><span>Secure, AI-powered accounts payable</span></footer>
        </main>
      </div>

      <input ref={fileInput} className="visually-hidden" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={(event) => handleUpload(event.target.files?.[0])} />
      {selected && <InvoiceDrawer invoice={selected} onClose={() => setSelected(null)} onChanged={updateRow} onMessage={notify} />}
      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span>{toast.kind === "success" ? <Check size={17} /> : <CircleAlert size={17} />}</span>{toast.message}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={15} /></button></div>}
    </div>
  );
}

function ScanLogo() {
  return <span className="scan-logo"><span /><span /><span /><span /></span>;
}

export default App;
