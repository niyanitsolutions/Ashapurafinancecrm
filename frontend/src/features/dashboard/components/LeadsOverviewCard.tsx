import { Card, CardHeader } from "@/components/cards/Card";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

type TrendPoint = { label: string; total: number; assigned: number; converted: number };

export function LeadsOverviewCard({ widgets }: { widgets: Widget[] | undefined }) {
  const sourceData = widgetData(widgets, "lead_source_chart");
  const items = Array.isArray(sourceData?.trend) ? sourceData.trend as TrendPoint[] : [];
  const max = Math.max(...items.map((item) => item.total), 1);
  return <Card><CardHeader title="Leads Overview" subtitle="Created, assigned and converted" icon={<span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon name="leads" className="h-4 w-4" /></span>} />
    {items.length === 0 ? <NoDataState icon="leads" message="No leads in the selected period" /> : <div className="space-y-3"><div className="flex gap-3 text-2xs text-textSecondary"><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-primary" />Created</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-success" />Assigned</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-info" />Converted</span></div><div className="max-h-60 space-y-2 overflow-y-auto pr-1">{items.map((item) => <div key={item.label} className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2 text-2xs"><span className="text-textSecondary">{item.label.slice(5)}</span><div className="space-y-1"><div className="h-2 rounded-full bg-background"><div className="h-full rounded-full bg-primary" style={{ width: `${(item.total / max) * 100}%` }} /></div><div className="h-1.5 rounded-full bg-background"><div className="h-full rounded-full bg-success" style={{ width: `${(item.assigned / max) * 100}%` }} /></div><div className="h-1.5 rounded-full bg-background"><div className="h-full rounded-full bg-info" style={{ width: `${(item.converted / max) * 100}%` }} /></div></div><span className="font-semibold text-text">{item.total}</span></div>)}</div></div>}
  </Card>;
}
