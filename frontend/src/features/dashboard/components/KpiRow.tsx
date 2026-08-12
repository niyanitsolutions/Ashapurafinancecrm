import { KpiCard } from "@/features/dashboard/components/KpiCard";
import { formatINRCompact } from "@/features/dashboard/format";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";

function numberValue(data: Record<string, unknown> | null, key = "value"): number | null {
  if (!data || typeof data[key] !== "number") return null;
  return data[key] as number;
}

// The 5 KPI cards. None of these 5 widgets carry real trend_direction/trend_percent data
// today (only applications_submitted/tasks_completed do, piloted elsewhere on this
// dashboard) — so no card fabricates a growth badge; each shows its real value plus an
// honest subtitle instead of an invented percentage.
export function KpiRow({ widgets }: { widgets: Widget[] | undefined }) {
  const totalLeads = numberValue(widgetData(widgets, "total_leads"));
  const assignedLeads = numberValue(widgetData(widgets, "assigned_leads"));
  const convertedCustomers = numberValue(widgetData(widgets, "customers_summary"));
  const disbursedAmount = numberValue(widgetData(widgets, "monthly_revenue"));
  const activePolicies = numberValue(widgetData(widgets, "policies_issued"));

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
      <KpiCard
        icon="leads"
        label="Total Leads"
        value={totalLeads === null ? "—" : totalLeads.toLocaleString("en-IN")}
        subtitle="All time"
      />
      <KpiCard
        icon="user"
        label="Assigned Leads"
        value={assignedLeads === null ? "—" : assignedLeads.toLocaleString("en-IN")}
        subtitle="All time"
      />
      <KpiCard
        icon="customers"
        label="Converted Customers"
        value={convertedCustomers === null ? "—" : convertedCustomers.toLocaleString("en-IN")}
        subtitle="All time"
      />
      <KpiCard
        icon="commission"
        label="Disbursed Amount"
        value={disbursedAmount === null ? "—" : formatINRCompact(disbursedAmount)}
        subtitle="This month"
      />
      <KpiCard
        icon="shield-check"
        label="Active Policies"
        value={activePolicies === null ? "—" : activePolicies.toLocaleString("en-IN")}
        subtitle="All time"
      />
    </div>
  );
}
