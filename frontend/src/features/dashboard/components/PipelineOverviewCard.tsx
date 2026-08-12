import { useState } from "react";
import { Card, CardHeader } from "@/components/cards/Card";
import { FunnelChart } from "@/components/charts/FunnelChart";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";

type PipelineTab = "loan" | "insurance";

// Both loan_pipeline_chart and insurance_pipeline_chart are real (group-by-status counts)
// but describe different, non-comparable stage sets — merging them into one funnel would
// misrepresent the data (a loan "Disbursed" stage summed with an insurance "Policy Issued"
// stage as if the same step). A small toggle keeps both real datasets available instead of
// arbitrarily picking one.
export function PipelineOverviewCard({ widgets }: { widgets: Widget[] | undefined }) {
  const [tab, setTab] = useState<PipelineTab>("loan");
  const data = widgetData(widgets, tab === "loan" ? "loan_pipeline_chart" : "insurance_pipeline_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];

  return (
    <Card>
      <CardHeader
        title="Pipeline Overview"
        subtitle="By current status"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="funnel" className="h-4 w-4" />
          </span>
        }
      />
      <div className="flex mb-5 -mt-2 w-fit rounded-lg border border-border p-0.5 text-2xs font-medium">
        {(["loan", "insurance"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md px-2.5 py-1 capitalize transition-colors ${
              tab === t ? "bg-primary text-white" : "text-textSecondary hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      {items.length === 0 ? <NoDataState icon="funnel" /> : <FunnelChart stages={items} />}
    </Card>
  );
}
