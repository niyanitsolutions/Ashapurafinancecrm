import { Card, CardHeader } from "@/components/cards/Card";
import { BarChart } from "@/components/charts/BarChart";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { formatINRCompact } from "@/features/dashboard/format";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function dateLabel(isoDate: string): string {
  const [year, m, day] = isoDate.split("-");
  const index = Number(m) - 1;
  const month = MONTH_NAMES[index];
  return month ? `${day ? `${Number(day)} ` : ""}${month} ${year}` : isoDate;
}

// Daily loan disbursements for the selected business-calendar period.
export function DisbursedTrendCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "revenue_trend_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];

  return (
    <Card>
      <CardHeader
        title="Disbursed Amount Trend"
        subtitle="Disbursed in selected period"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="commission" className="h-4 w-4" />
          </span>
        }
      />
      {items.length === 0 ? (
        <NoDataState icon="commission" />
      ) : (
        <div className="overflow-x-auto"><div style={{ minWidth: Math.max(items.length * 72, 240) }}>
          <BarChart data={items.map((i) => ({ label: dateLabel(i.label), value: i.value }))} formatValue={formatINRCompact} />
        </div></div>
      )}
    </Card>
  );
}
