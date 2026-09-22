import { useEffect } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { DisbursedTrendCard } from "@/features/dashboard/components/DisbursedTrendCard";
import { KpiRow } from "@/features/dashboard/components/KpiRow";
import { LeadSourcesCard } from "@/features/dashboard/components/LeadSourcesCard";
import { LeadsOverviewCard } from "@/features/dashboard/components/LeadsOverviewCard";
import { PipelineOverviewCard } from "@/features/dashboard/components/PipelineOverviewCard";
import { RecentActivitiesCard } from "@/features/dashboard/components/RecentActivitiesCard";
import { getErrorMessage } from "@/features/dashboard/errors";
import { useDashboardFilters } from "@/features/dashboard/DashboardFiltersContext";
import { useDashboardWidgets, widgetData } from "@/features/dashboard/useDashboardWidgets";

export function DashboardPage() {
  const { data: widgets, isLoading, isFetching, error } = useDashboardWidgets();
  const { setSources } = useDashboardFilters();
  useEffect(() => {
    const data = widgetData(widgets, "lead_source_chart");
    if (!widgets) return;
    const items = Array.isArray(data?.source_options) ? data.source_options as { id?: string; label: string }[] : [];
    setSources(items.filter((item): item is { id: string; label: string } => Boolean(item.id)).map(({ id, label }) => ({ id, label })));
  }, [widgets, setSources]);

  return <div className="space-y-6 p-4 sm:p-6 lg:p-8">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-bold text-text">Performance overview</h2><p className="mt-1 text-sm text-textSecondary">Live, permission-scoped results for the selected period.</p></div>{isFetching && !isLoading && <span className="text-2xs font-medium text-textSecondary" role="status">Refreshing dashboard…</span>}</div>
    {error && <ErrorBanner message={getErrorMessage(error)} />}
    {isLoading && !widgets ? <div className="rounded-card border border-border bg-card p-8 text-sm text-textSecondary" role="status">Loading dashboard…</div> : null}
    {widgets && <><KpiRow widgets={widgets} /><div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><LeadsOverviewCard widgets={widgets} /><LeadSourcesCard widgets={widgets} /><PipelineOverviewCard widgets={widgets} /></div><div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><DisbursedTrendCard widgets={widgets} /><div className="xl:col-span-2"><RecentActivitiesCard widgets={widgets} /></div></div></>}
  </div>;
}
