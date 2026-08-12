import { Card, CardHeader } from "@/components/cards/Card";
import { DonutChart } from "@/components/charts/DonutChart";
import { NoDataState } from "@/components/charts/NoDataState";
import { assignCategoricalColors } from "@/components/charts/chartColors";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

export function LeadSourcesCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "lead_source_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];
  const total = items.reduce((sum, i) => sum + i.value, 0);

  return (
    <Card>
      <CardHeader
        title="Lead Sources"
        subtitle="Share of total leads"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="leads" className="h-4 w-4" />
          </span>
        }
      />
      {items.length === 0 ? (
        <NoDataState icon="leads" />
      ) : (
        <DonutChart segments={assignCategoricalColors(items)} centerLabel="Total" centerValue={total.toLocaleString("en-IN")} />
      )}
    </Card>
  );
}
