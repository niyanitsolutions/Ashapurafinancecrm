import { Card, CardHeader } from "@/components/cards/Card";
import { BarChart } from "@/components/charts/BarChart";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { formatINRCompact } from "@/features/dashboard/format";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthLabel(yyyyMm: string): string {
  const [, m] = yyyyMm.split("-");
  const index = Number(m) - 1;
  return MONTH_NAMES[index] ?? yyyyMm;
}

// revenue_trend_chart — real, last 6 calendar months of combined loan+insurance revenue.
// The reference calls the equivalent slot "Disbursed Amount Trend"; this is the closest
// real time series (see dashboard redesign notes on the KPI row's "Disbursed Amount" using
// the same underlying figure).
export function DisbursedTrendCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "revenue_trend_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];

  return (
    <Card>
      <CardHeader
        title="Disbursed Amount Trend"
        subtitle="Last 6 months"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="commission" className="h-4 w-4" />
          </span>
        }
      />
      {items.length === 0 ? (
        <NoDataState icon="commission" />
      ) : (
        <BarChart data={items.map((i) => ({ label: monthLabel(i.label), value: i.value }))} formatValue={formatINRCompact} />
      )}
    </Card>
  );
}
