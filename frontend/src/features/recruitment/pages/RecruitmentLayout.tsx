import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getRecruitmentCounts, type RecruitmentCounts } from "@/features/recruitment/api";
import { usePermissions } from "@/features/access_control/usePermissions";

const COUNT_POLL_INTERVAL_MS = 15_000;
const BASE = "/insurance-management/recruitment";

export interface RecruitmentOutletContext {
  refreshCounts: () => void;
}

export function RecruitmentLayout() {
  const { can } = usePermissions();
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
  // Each tab is filtered by its effective child View permission. The API independently
  // enforces the same stage permission and existing record visibility rules.
  const tabs = [
    { key: "fresh", label: "Fresh Leads", to: `${BASE}/fresh`, matchKey: "insurance_cases", count: counts?.fresh },
    { key: "bop", label: "BOP", to: `${BASE}/bop`, matchKey: "insurance_cases", count: counts?.bop },
    { key: "doc_collection", label: "Doc Collection", to: `${BASE}/doc-collection`, matchKey: "insurance_cases", count: counts?.doc_collection },
    { key: "exam_fee_status", label: "Exam Fee Status", to: `${BASE}/exam-fee-status`, matchKey: "insurance_cases", count: counts?.exam_fee_status },
    { key: "examination", label: "Examination", to: `${BASE}/examination`, matchKey: "insurance_cases", count: counts?.examination },
    { key: "re_examination", label: "Re-Examination", to: `${BASE}/re-examination`, matchKey: "insurance_cases", count: counts?.re_examination },
    { key: "agency_code", label: "Agency Code", to: `${BASE}/agency-code`, matchKey: "insurance_cases", count: counts?.agency_code },
    { key: "rejected", label: "Rejected", to: `${BASE}/rejected`, matchKey: "insurance_cases", count: counts?.rejected },
  ].filter((tab) => can(`insurance_management:recruitment.${tab.key}`, "view"));

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts } satisfies RecruitmentOutletContext} />
    </>
  );
}
