import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getRecruitmentCounts, type RecruitmentCounts } from "@/features/recruitment/api";

const COUNT_POLL_INTERVAL_MS = 15_000;
const BASE = "/insurance-management/recruitment";

export interface RecruitmentOutletContext {
  refreshCounts: () => void;
}

export function RecruitmentLayout() {
  const [counts, setCounts] = useState<RecruitmentCounts | null>(null);

  const loadCounts = useCallback(() => {
    getRecruitmentCounts()
      .then(setCounts)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    loadCounts();
    const interval = window.setInterval(loadCounts, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [loadCounts]);

  // 2026 redesign: one flat top-level tab per recruitment stage (Doc Collection is its
  // own stage, no longer a parent of Examination / Re-Examination / Agency Code). Like
  // Policy Leads, these tabs are visible to anyone who can enter Insurance Management;
  // the API scopes the count and list rows, never tab visibility.
  const tabs = [
    { label: "Fresh Leads", to: `${BASE}/fresh`, matchKey: "insurance_cases", count: counts?.fresh },
    { label: "BOP", to: `${BASE}/bop`, matchKey: "insurance_cases", count: counts?.bop },
    { label: "Doc Collection", to: `${BASE}/doc-collection`, matchKey: "insurance_cases", count: counts?.doc_collection },
    { label: "Exam Fee Status", to: `${BASE}/exam-fee-status`, matchKey: "insurance_cases", count: counts?.exam_fee_status },
    { label: "Examination", to: `${BASE}/examination`, matchKey: "insurance_cases", count: counts?.examination },
    { label: "Re-Examination", to: `${BASE}/re-examination`, matchKey: "insurance_cases", count: counts?.re_examination },
    { label: "Agency Code", to: `${BASE}/agency-code`, matchKey: "insurance_cases", count: counts?.agency_code },
    { label: "Rejected", to: `${BASE}/rejected`, matchKey: "insurance_cases", count: counts?.rejected },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts } satisfies RecruitmentOutletContext} />
    </>
  );
}
