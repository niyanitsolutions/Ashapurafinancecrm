import { Link } from "react-router-dom";
import type { Widget } from "@/features/dashboard/api";
import { DonutChart } from "@/features/dashboard/components/DonutChart";
import { LineChart } from "@/features/dashboard/components/LineChart";
import { MiniBarList } from "@/features/dashboard/components/MiniBarList";
import { Icon, type IconName } from "@/theme/icons";

// Display-only icon per widget (KPI card icon, per the enterprise-redesign brief) — purely
// a frontend lookup keyed off the same catalog key already used by WIDGET_ROUTES/
// LABEL_OVERRIDES above; falls back to a generic "grid" glyph for any widget not listed.
const WIDGET_ICONS: Record<string, IconName> = {
  today_leads: "leads",
  assigned_leads: "leads",
  total_leads: "leads",
  lead_conversion_rate: "leads",
  lead_source_chart: "leads",
  disbursed: "loan",
  rejected: "loan",
  tasks: "tasks",
  tasks_completed: "tasks",
  notifications: "bell",
  department_summary: "departments",
  employee_summary: "employees",
  employee_performance_chart: "employees",
  referral_summary: "referral",
  referral_performance_chart: "referral",
  customers_summary: "customers",
  applications_summary: "applications",
  applications_submitted: "applications",
  loan_cases_total: "loan",
  loan_pipeline_chart: "loan",
  loan_re_eligible: "re-eligible",
  loan_revenue: "loan",
  insurance_cases_total: "insurance",
  insurance_pipeline_chart: "insurance",
  policies_issued: "insurance",
  insurance_rejected: "insurance",
  insurance_re_eligible: "re-eligible",
  insurance_revenue: "insurance",
  monthly_revenue: "reports",
  revenue_trend_chart: "reports",
  referral_pending_commission: "commission",
  referral_paid_commission: "commission",
  recent_activities: "clock",
  today_performance: "dashboard",
  monthly_performance: "dashboard",
};

// Where each widget navigates when clicked — only widgets with a real destination page
// are mapped; the rest have no backing page yet and stay non-interactive rather than
// linking somewhere fake.
const WIDGET_ROUTES: Record<string, string> = {
  today_leads: "/leads",
  assigned_leads: "/leads",
  total_leads: "/leads",
  lead_conversion_rate: "/leads",
  disbursed: "/loan-cases?status=disbursed",
  rejected: "/loan-cases?status=rejected",
  tasks: "/tasks",
  tasks_completed: "/tasks",
  notifications: "/notifications",
  department_summary: "/settings/departments",
  employee_summary: "/employees",
  referral_summary: "/referral-partners",
  customers_summary: "/customers",
  applications_summary: "/applications",
  applications_submitted: "/applications",
  loan_cases_total: "/loan-cases",
  loan_pipeline_chart: "/loan-cases",
  loan_re_eligible: "/loan-management/re-eligible",
  insurance_cases_total: "/insurance-cases",
  insurance_pipeline_chart: "/insurance-cases",
  policies_issued: "/insurance-management/policies-issued",
  insurance_rejected: "/insurance-cases?status=rejected",
  insurance_re_eligible: "/insurance-management/re-eligible",
  referral_pending_commission: "/commission-ledger?status=pending",
  referral_paid_commission: "/commission-ledger?status=paid",
  referral_performance_chart: "/referral-partners",
};

// Display-only relabeling — the backend catalog (dashboard_widgets) keeps its original
// keys/labels; this just makes the card headings read more like business language.
const LABEL_OVERRIDES: Record<string, string> = {
  department_summary: "Team by Department",
  employee_summary: "Team Size",
  referral_summary: "Channel Partners",
};

// Phase 4.1 chart-type consistency convention (applied to every chart this Phase
// introduced — the one pre-existing chart, `department_summary`, ships from an earlier,
// frozen module and is left exactly as it already was):
//   - Bar: counts by category (Lead Source, Pipeline stage, Employee/Referral Performance)
//   - Line: trends over time (Revenue Trend)
//   - Donut: reserved for genuine "share of one whole" composition widgets
// Never more than one chart type for the same kind of metric across the dashboard.
const DONUT_CHART_WIDGETS = new Set(["department_summary"]);
const BAR_CHART_WIDGETS = new Set([
  "lead_source_chart",
  "loan_pipeline_chart",
  "insurance_pipeline_chart",
  "employee_performance_chart",
  "referral_performance_chart",
]);
const LINE_CHART_WIDGETS = new Set(["revenue_trend_chart"]);

function formatCurrency(value: unknown): string {
  const n = typeof value === "number" ? value : 0;
  return `₹${n.toLocaleString("en-IN")}`;
}

function MetricBody({ widgetKey, data }: { widgetKey: string; data: Record<string, unknown> }) {
  if (data.available === false) {
    return <p className="text-sm text-text/40">Coming soon</p>;
  }

  if (widgetKey === "applications_summary") {
    return (
      <div>
        <p className="text-2xl font-bold text-text">{String(data.total ?? 0)}</p>
        <p className="text-xs text-text/50">
          {String(data.submitted ?? 0)} submitted · {String(data.draft ?? 0)} draft
        </p>
      </div>
    );
  }

  if (widgetKey === "referral_pending_commission" || widgetKey === "referral_paid_commission") {
    return (
      <div>
        <p className="text-2xl font-bold text-text">{formatCurrency(data.amount)}</p>
        <p className="text-xs text-text/50">{String(data.value ?? 0)} entries</p>
      </div>
    );
  }

  if (widgetKey === "monthly_revenue") {
    return (
      <div>
        <p className="text-2xl font-bold text-text">{formatCurrency(data.value)}</p>
        <p className="text-xs text-text/50">
          Loan {formatCurrency(data.loan)} · Insurance {formatCurrency(data.insurance)}
        </p>
      </div>
    );
  }

  if (widgetKey === "loan_revenue" || widgetKey === "insurance_revenue") {
    return <p className="text-2xl font-bold text-text">{formatCurrency(data.value)}</p>;
  }

  if (widgetKey === "lead_conversion_rate") {
    return <p className="text-2xl font-bold text-text">{String(data.value ?? 0)}%</p>;
  }

  if (widgetKey === "today_performance" || widgetKey === "monthly_performance") {
    return (
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-lg font-semibold text-text">{String(data.leads ?? 0)}</p>
          <p className="text-[11px] text-text/50">Leads</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-text">{String(data.applications ?? 0)}</p>
          <p className="text-[11px] text-text/50">Applications</p>
        </div>
        <div>
          <p className="text-lg font-semibold text-text">{String(data.tasks ?? 0)}</p>
          <p className="text-[11px] text-text/50">Tasks Done</p>
        </div>
      </div>
    );
  }

  if (typeof data.total === "number") {
    return (
      <div>
        <p className="text-2xl font-bold text-text">{data.total}</p>
        <p className="text-xs text-text/50">
          {String(data.active ?? 0)} active · {String(data.inactive ?? 0)} inactive
        </p>
      </div>
    );
  }
  return <p className="text-2xl font-bold text-text">{String(data.value ?? 0)}</p>;
}

function ListBody({ widgetKey, data }: { widgetKey: string; data: Record<string, unknown> }) {
  if (data.available === false) {
    return <p className="text-sm text-text/40">Coming soon</p>;
  }
  const items = Array.isArray(data.items) ? data.items : [];

  if (DONUT_CHART_WIDGETS.has(widgetKey)) {
    if (items.length === 0) return <p className="text-sm text-text/40">Nothing here yet.</p>;
    return <DonutChart data={(items as { label: string; value: number }[]).map((row) => ({ label: row.label, value: row.value }))} />;
  }

  if (BAR_CHART_WIDGETS.has(widgetKey)) {
    if (items.length === 0) return <p className="text-sm text-text/40">Nothing here yet.</p>;
    return <MiniBarList data={items as { label: string; value: number }[]} />;
  }

  if (LINE_CHART_WIDGETS.has(widgetKey)) {
    if (items.length === 0) return <p className="text-sm text-text/40">Nothing here yet.</p>;
    return <LineChart data={items as { label: string; value: number }[]} />;
  }

  if (items.length === 0) {
    return <p className="text-sm text-text/40">Nothing here yet.</p>;
  }

  if (widgetKey === "recent_activities") {
    return (
      <ul className="space-y-1">
        {(items as { event_type: string; created_at: string | null }[]).map((row, i) => (
          <li key={i} className="text-sm text-text/70">
            <span className="text-text capitalize">{row.event_type.replace(/_/g, " ")}</span>
            {row.created_at && <span className="text-text/40"> — {new Date(row.created_at).toLocaleString()}</span>}
          </li>
        ))}
      </ul>
    );
  }

  if (widgetKey === "tasks") {
    return (
      <ul className="space-y-1.5">
        {(items as { title: string; due_at: string | null }[]).map((row, i) => (
          <li key={i} className="text-sm">
            <span className="text-text">{row.title}</span>
            {row.due_at && <span className="text-text/40"> — due {new Date(row.due_at).toLocaleDateString()}</span>}
          </li>
        ))}
      </ul>
    );
  }

  if (widgetKey === "notifications") {
    return (
      <ul className="space-y-1.5">
        {(items as { title: string; status: string }[]).map((row, i) => (
          <li key={i} className="text-sm flex items-center gap-2">
            {row.status === "unread" && <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
            <span className={row.status === "unread" ? "text-text font-medium" : "text-text/60"}>{row.title}</span>
          </li>
        ))}
      </ul>
    );
  }

  return <p className="text-sm text-text/60">{items.length} item(s)</p>;
}

// Phase 4.1 Widget Standard — Trend/Comparison/Last Updated/View Details are optional,
// generic slots: any widget whose provider includes `trend_direction`/`comparison_label`/
// `last_updated` gets this treatment automatically, with no per-widget-key special case
// needed here. Only two providers populate them today (`applications_submitted`,
// `tasks_completed`, piloting the standard) — every other widget simply omits the fields
// and renders exactly as before.
function TrendIndicator({ data }: { data: Record<string, unknown> }) {
  if (typeof data.trend_direction !== "string") return null;
  const direction = data.trend_direction;
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "→";
  const color = direction === "up" ? "text-success" : direction === "down" ? "text-danger" : "text-text/40";
  return (
    <div className="mt-2 flex items-center gap-1.5 text-xs">
      <span className={`${color} font-medium`}>
        {arrow} {String(data.trend_percent ?? 0)}%
      </span>
      {typeof data.comparison_label === "string" && <span className="text-text/40">{data.comparison_label}</span>}
    </div>
  );
}

function LastUpdatedLabel({ value }: { value: unknown }) {
  if (typeof value !== "string") return null;
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  const label =
    seconds < 60 ? "just now" : seconds < 3600 ? `${Math.floor(seconds / 60)} minute(s) ago` : new Date(value).toLocaleString();
  return <p className="mt-2 text-[10px] text-text/30">Updated {label}</p>;
}

export function WidgetCard({ widget }: { widget: Widget }) {
  const to = WIDGET_ROUTES[widget.key];
  const label = LABEL_OVERRIDES[widget.key] ?? widget.label;
  const icon = WIDGET_ICONS[widget.key] ?? "grid";

  const content = (
    <>
      <div className="absolute inset-x-0 top-0 h-1 rounded-t-card bg-gradient-to-r from-primary via-primary-light to-info" />
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary shrink-0">
            <Icon name={icon} className="h-[18px] w-[18px]" />
          </span>
          <h3 className="text-sm font-medium text-textSecondary">{label}</h3>
        </div>
        {widget.is_pinned && <span title="Pinned" className="text-primary text-xs">📌</span>}
      </div>
      {widget.data ? (
        widget.widget_type === "metric" ? (
          <MetricBody widgetKey={widget.key} data={widget.data} />
        ) : (
          <ListBody widgetKey={widget.key} data={widget.data} />
        )
      ) : (
        <p className="text-sm text-text/40">Loading…</p>
      )}
      {widget.data && <TrendIndicator data={widget.data} />}
      {widget.data && <LastUpdatedLabel value={widget.data.last_updated} />}
      {to && <p className="mt-2 text-xs font-semibold text-primary">View Details →</p>}
    </>
  );

  const className = `hover-lift animate-slide-up relative overflow-hidden block bg-card border border-border rounded-card shadow-card p-5 ${to ? "hover:border-primary/30 cursor-pointer" : ""}`;

  if (to) {
    return (
      <Link to={to} className={className}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
