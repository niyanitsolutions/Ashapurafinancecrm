import { Card, CardHeader } from "@/components/cards/Card";
import { DonutChart } from "@/components/charts/DonutChart";
import { NoDataState } from "@/components/charts/NoDataState";
import { BRAND_ORANGE, CATEGORICAL } from "@/components/charts/chartColors";
import type { Widget } from "@/features/dashboard/api";
import { formatINRCompact } from "@/features/dashboard/format";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

// The reference's "Business Mix" splits disbursed amount by loan *product type* (Business/
// Personal/Home Loan, LAP) — no widget aggregates revenue by product category (see
// dashboard redesign notes). The real, available split is Loan vs Insurance revenue
// (monthly_revenue.{loan,insurance}), so this card is honestly relabeled "Revenue Mix"
// rather than pretending to show product-level data that doesn't exist.
export function RevenueMixCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "monthly_revenue");
  const loan = typeof data?.loan === "number" ? data.loan : null;
  const insurance = typeof data?.insurance === "number" ? data.insurance : null;
  const total = (loan ?? 0) + (insurance ?? 0);

  return (
    <Card>
      <CardHeader
        title="Revenue Mix"
        subtitle="Loan vs. Insurance, this month"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="reports" className="h-4 w-4" />
          </span>
        }
      />
      {loan === null || insurance === null || total === 0 ? (
        <NoDataState icon="reports" />
      ) : (
        <DonutChart
          segments={[
            { label: "Loan", value: loan, color: BRAND_ORANGE },
            { label: "Insurance", value: insurance, color: CATEGORICAL[0] },
          ]}
          centerLabel="Total"
          centerValue={formatINRCompact(total)}
          formatValue={formatINRCompact}
        />
      )}
    </Card>
  );
}
