import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getLoanCaseCounts, type LoanCaseCounts } from "@/features/loan_management/api";
import { usePermissions } from "@/features/access_control/usePermissions";

// Loan pipeline tabs (decision #129) — one tab per LoanStatus.ALL value except
// `re_eligible`, whose tab moved to Leads (/leads/re-eligible) per production spec. Each
// has a live, server-computed count badge (GET /loan-cases/counts), same "never trust
// the currently loaded page" principle Leads' own tab counts established (decision 125).
const COUNT_POLL_INTERVAL_MS = 15_000;

export function LoanManagementLayout() {
  const { can } = usePermissions();
  const [counts, setCounts] = useState<LoanCaseCounts | null>(null);

  useEffect(() => {
    const load = () => getLoanCaseCounts().then(setCounts).catch(() => undefined);
    load();
    const interval = window.setInterval(load, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  const tabs = [
    { key: "new_customer", label: "Loan Cases", to: "/loan-management/cases", exact: true, count: counts?.new_customer },
    { key: "credit_evaluation", label: "Credit Evaluation", to: "/loan-management/credit-evaluation", count: counts?.credit_evaluation },
    { key: "offer_acceptance", label: "Offer Acceptance", to: "/loan-management/offer-acceptance", count: counts?.offer_acceptance },
    { key: "additional_documents", label: "Additional Documents", to: "/loan-management/additional-documents", count: counts?.additional_documents },
    { key: "rv_ov_ref", label: "RV/OV/Ref", to: "/loan-management/rv-ov-ref", count: counts?.rv_ov_ref },
    { key: "esign_nach_kyc", label: "eSign / NACH / KYC", to: "/loan-management/esign-nach-kyc", count: counts?.esign_nach_kyc },
    { key: "final_evaluation", label: "Final Evaluation", to: "/loan-management/final-evaluation", count: counts?.final_evaluation },
    { key: "send_for_disbursement", label: "Send For Disbursement", to: "/loan-management/send-for-disbursement", count: counts?.send_for_disbursement },
    { key: "disbursed", label: "Disbursed", to: "/loan-management/disbursements", count: counts?.disbursed },
    { key: "on_hold", label: "On Hold", to: "/loan-management/on-hold", count: counts?.on_hold },
    // "Re-Eligible" tab moved to Leads (/leads/re-eligible) per production spec — the
    // re_eligible status, its list API and counts are unchanged.
    { key: "rejected", label: "Rejected", to: "/loan-management/rejected", count: counts?.rejected },
  ].filter((tab) => can(`loan_management:applications.${tab.key}`, "view"));

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet />
    </>
  );
}
