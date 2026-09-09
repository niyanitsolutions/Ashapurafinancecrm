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
  // own stage, no longer a parent of Examination / Re-Examination / Agency Code).
  const tabs = [
    { label: "Fresh Leads", to: `${BASE}/fresh`, matchKey: "recruitment_leads", count: counts?.fresh },
    { label: "BOP", to: `${BASE}/bop`, matchKey: "recruitment_leads", count: counts?.bop },
    { label: "Doc Collection", to: `${BASE}/doc-collection`, matchKey: "recruitment_leads", count: counts?.doc_collection },
    { label: "Exam Fee Status", to: `${BASE}/exam-fee-status`, matchKey: "recruitment_leads", count: counts?.exam_fee_status },
    { label: "Examination", to: `${BASE}/examination`, matchKey: "recruitment_leads", count: counts?.examination },
    { label: "Re-Examination", to: `${BASE}/re-examination`, matchKey: "recruitment_leads", count: counts?.re_examination },
    { label: "Agency Code", to: `${BASE}/agency-code`, matchKey: "recruitment_leads", count: counts?.agency_code },
    { label: "Rejected", to: `${BASE}/rejected`, matchKey: "recruitment_leads", count: counts?.rejected },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts } satisfies RecruitmentOutletContext} />
    </>
  );
}
