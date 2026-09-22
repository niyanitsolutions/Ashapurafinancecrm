import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardHeader } from "@/components/cards/Card";
import { FunnelChart } from "@/components/charts/FunnelChart";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon } from "@/theme/icons";
import { useDashboardFilters } from "@/features/dashboard/DashboardFiltersContext";

type PipelineTab = "loan" | "insurance";

// Both loan_pipeline_chart and insurance_pipeline_chart are real (group-by-status counts)
// but describe different, non-comparable stage sets — merging them into one funnel would
// misrepresent the data (a loan "Disbursed" stage summed with an insurance "Policy Issued"
// stage as if the same step). A small toggle keeps both real datasets available instead of
// arbitrarily picking one.
export function PipelineOverviewCard({ widgets }: { widgets: Widget[] | undefined }) {
  const [selectedTab, setTab] = useState<PipelineTab>("loan");
  const { filters } = useDashboardFilters();
  const tab = filters.productCategory ?? selectedTab;
  const navigate = useNavigate();
  const data = widgetData(widgets, tab === "loan" ? "loan_pipeline_chart" : "insurance_pipeline_chart");
  const items = Array.isArray(data?.items) ? (data!.items as { label: string; value: number }[]) : [];

  return (
    <Card>
      <CardHeader
        title="Pipeline Overview"
        subtitle="Cases updated in selected period"
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
            disabled={Boolean(filters.productCategory && filters.productCategory !== t)}
            className={`rounded-md px-2.5 py-1 capitalize transition-colors ${
              tab === t ? "bg-primary text-white" : "text-textSecondary hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      {items.length === 0 ? <NoDataState icon="funnel" /> : <FunnelChart stages={items} onStageClick={(stage) => {
        const status = stage.status;
        const loanRoutes: Record<string, string> = { new_customer: "/loan-management/cases", credit_evaluation: "/loan-management/credit-evaluation", offer_acceptance: "/loan-management/offer-acceptance", additional_documents: "/loan-management/additional-documents", rv_ov_ref: "/loan-management/rv-ov-ref", esign_nach_kyc: "/loan-management/esign-nach-kyc", final_evaluation: "/loan-management/final-evaluation", send_for_disbursement: "/loan-management/send-for-disbursement", on_hold: "/loan-management/on-hold", rejected: "/loan-management/rejected" };
        const insuranceRoutes: Record<string, string> = { fresh_lead: "/insurance-management/fresh-leads", policy_document: "/insurance-management/policy-document", policy_login: "/insurance-management/policy-login", payment: "/insurance-management/payment", policy_issued: "/insurance-management/policy-issued", on_hold: "/insurance-management/on-hold", rejected: "/insurance-management/rejected" };
        loanRoutes.disbursed = "/loan-management/disbursements";
        loanRoutes.re_eligible = "/leads/re-eligible";
        insuranceRoutes.re_eligible = "/insurance-management/re-eligible";
        const route = (tab === "loan" ? loanRoutes : insuranceRoutes)[status ?? ""];
        if (route) navigate(route);
      }} />}
    </Card>
  );
}
