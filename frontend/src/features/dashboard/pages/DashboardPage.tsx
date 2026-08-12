import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getLayout, updateLayout, type Widget } from "@/features/dashboard/api";
import { DisbursedTrendCard } from "@/features/dashboard/components/DisbursedTrendCard";
import { KpiRow } from "@/features/dashboard/components/KpiRow";
import { LeadSourcesCard } from "@/features/dashboard/components/LeadSourcesCard";
import { LeadsOverviewCard } from "@/features/dashboard/components/LeadsOverviewCard";
import { PipelineOverviewCard } from "@/features/dashboard/components/PipelineOverviewCard";
import { RecentActivitiesCard } from "@/features/dashboard/components/RecentActivitiesCard";
import { RevenueMixCard } from "@/features/dashboard/components/RevenueMixCard";
import { TaskOverviewRow } from "@/features/dashboard/components/TaskOverviewRow";
import { TopEmployeesCard } from "@/features/dashboard/components/TopEmployeesCard";
import { getErrorMessage } from "@/features/dashboard/errors";
import { useDashboardWidgets } from "@/features/dashboard/useDashboardWidgets";

// The 9 widget keys this fixed layout actually renders — Customize now only ever edits
// visibility/refresh-interval for these, not the full catalog. Any other widget a user's
// old layout preference had pinned/reordered (Referral Summary, Department Summary,
// Re-Eligible counts, ...) no longer has a slot on this page — see the dashboard redesign
// notes on the fixed-layout-vs-dynamic-catalog decision.
const TEMPLATE_WIDGET_KEYS = [
  "total_leads",
  "assigned_leads",
  "customers_summary",
  "monthly_revenue",
  "policies_issued",
  "lead_source_chart",
  "loan_pipeline_chart",
  "insurance_pipeline_chart",
  "revenue_trend_chart",
  "employee_performance_chart",
  "tasks",
  "tasks_completed",
  "recent_activities",
];

// Pin/hide/reorder-to-arbitrary-position doesn't map onto a fixed grid (each card has one
// designated slot, not a free position) — so Customize now only offers what still means
// something here: show/hide a card, and how often it polls for fresh data.
function CustomizePanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [rows, setRows] = useState<Widget[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getLayout()
      .then((widgets) => setRows(widgets.filter((w) => TEMPLATE_WIDGET_KEYS.includes(w.key))))
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  const toggleVisible = (key: string) => {
    setRows((prev) => prev && prev.map((r) => (r.key === key ? { ...r, is_visible: !r.is_visible } : r)));
  };

  const setRefresh = (key: string, seconds: number) => {
    setRows((prev) => prev && prev.map((r) => (r.key === key ? { ...r, refresh_interval_seconds: seconds } : r)));
  };

  const onSave = async () => {
    if (!rows) return;
    setError(null);
    setIsSaving(true);
    try {
      await updateLayout(
        rows.map((r) => ({
          widget_key: r.key, is_visible: r.is_visible, order: r.order,
          refresh_interval_seconds: r.refresh_interval_seconds, is_pinned: r.is_pinned,
        })),
      );
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl shadow-card p-5 mb-6">
      <ErrorBanner message={error} />
      <p className="text-2xs text-textSecondary mb-4">Show or hide a card, and set how often it refreshes. This only changes your own view.</p>
      {rows === null ? (
        <p className="text-sm text-textSecondary">Loading…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-textSecondary border-b border-border">
              <th className="py-2 font-medium">Card</th>
              <th className="py-2 font-medium">Visible</th>
              <th className="py-2 font-medium">Refresh (sec)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-border last:border-0">
                <td className="py-2.5 text-text">{row.label}</td>
                <td className="py-2.5">
                  <input type="checkbox" checked={row.is_visible} onChange={() => toggleVisible(row.key)} />
                </td>
                <td className="py-2.5">
                  <input
                    type="number"
                    min={10}
                    max={3600}
                    className="w-20 rounded border border-border px-2 py-1"
                    value={row.refresh_interval_seconds}
                    onChange={(e) => setRefresh(row.key, Number(e.target.value) || 300)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-4 flex gap-3">
        <button
          type="button"
          className="rounded-lg bg-primary text-white text-sm font-medium py-2 px-4 disabled:opacity-50"
          disabled={isSaving || rows === null}
          onClick={onSave}
        >
          {isSaving ? "Saving…" : "Save"}
        </button>
        <button type="button" className="text-sm text-textSecondary hover:underline" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { data: widgets, isLoading, error } = useDashboardWidgets();
  const [isCustomizing, setIsCustomizing] = useState(false);
  const queryClient = useQueryClient();

  return (
    <div className="p-6 lg:p-8 space-y-8">
      <div className="flex items-center justify-end">
        <button
          type="button"
          className="flex items-center gap-1.5 text-2xs font-medium text-primary border border-primary/30 rounded-lg px-3 py-1.5 hover:bg-primary/5"
          onClick={() => setIsCustomizing((v) => !v)}
        >
          {isCustomizing ? "Close" : "Customize"}
        </button>
      </div>

      {error && <ErrorBanner message={getErrorMessage(error)} />}

      {isCustomizing && (
        <CustomizePanel
          onClose={() => setIsCustomizing(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ["dashboard-widgets"] })}
        />
      )}

      {isLoading && !widgets && <p className="text-sm text-textSecondary">Loading…</p>}

      {widgets && (
        <>
          <KpiRow widgets={widgets} />

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <LeadsOverviewCard />
            <LeadSourcesCard widgets={widgets} />
            <PipelineOverviewCard widgets={widgets} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <DisbursedTrendCard widgets={widgets} />
            <RevenueMixCard widgets={widgets} />
            <TopEmployeesCard widgets={widgets} />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div className="xl:col-span-2">
              <TaskOverviewRow widgets={widgets} />
            </div>
            <RecentActivitiesCard widgets={widgets} />
          </div>
        </>
      )}
    </div>
  );
}
