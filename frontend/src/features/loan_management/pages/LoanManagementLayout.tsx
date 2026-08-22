import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getLoanCaseCounts, type LoanCaseCounts } from "@/features/loan_management/api";

// 12-tab pipeline (decision #129) — one tab per LoanStatus.ALL value, each with a live,
// server-computed count badge (GET /loan-cases/counts), same "never trust the currently
// loaded page" principle Leads' own tab counts established (decision 125).
const COUNT_POLL_INTERVAL_MS = 15_000;

export function LoanManagementLayout() {
  const [counts, setCounts] = useState<LoanCaseCounts | null>(null);

  useEffect(() => {
    const load = () => getLoanCaseCounts().then(setCounts).catch(() => undefined);
    load();
    const interval = window.setInterval(load, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  const tabs = [
    { label: "Loan Cases", to: "/loan-management/cases", exact: true, count: counts?.new_customer },
    { label: "Credit Evaluation", to: "/loan-management/credit-evaluation", count: counts?.credit_evaluation },
    { label: "Offer Acceptance", to: "/loan-management/offer-acceptance", count: counts?.offer_acceptance },
    { label: "Additional Documents", to: "/loan-management/additional-documents", count: counts?.additional_documents },
    { label: "RV/OV/Ref", to: "/loan-management/rv-ov-ref", count: counts?.rv_ov_ref },
    { label: "eSign / NACH / KYC", to: "/loan-management/esign-nach-kyc", count: counts?.esign_nach_kyc },
    { label: "Final Evaluation", to: "/loan-management/final-evaluation", count: counts?.final_evaluation },
    { label: "Send For Disbursement", to: "/loan-management/send-for-disbursement", count: counts?.send_for_disbursement },
    { label: "Disbursed", to: "/loan-management/disbursements", count: counts?.disbursed },
    { label: "On Hold", to: "/loan-management/on-hold", count: counts?.on_hold },
    { label: "Re-Eligible", to: "/loan-management/re-eligible", count: counts?.re_eligible },
    { label: "Rejected", to: "/loan-management/rejected", count: counts?.rejected },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet />
    </>
  );
}
