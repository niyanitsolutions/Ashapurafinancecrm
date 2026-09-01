import { useCallback, useEffect, useState } from "react";
import { Outlet, useOutletContext } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getRecruitmentCounts, type RecruitmentCounts } from "@/features/recruitment/api";
import type { RecruitmentOutletContext } from "@/features/recruitment/pages/RecruitmentLayout";

const BASE = "/insurance-management/recruitment/doc-collection";

export function DocCollectionLayout() {
  const parent = useOutletContext<RecruitmentOutletContext>();
  const [counts, setCounts] = useState<RecruitmentCounts | null>(null);

  const loadCounts = useCallback(() => {
    getRecruitmentCounts()
      .then(setCounts)
      .catch(() => undefined);
    parent.refreshCounts();
  }, [parent]);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  const tabs = [
    { label: "Examination", to: `${BASE}/examination`, matchKey: "recruitment_leads", count: counts?.examination },
    {
      label: "Re-Examination",
      to: `${BASE}/re-examination`,
      matchKey: "recruitment_leads",
      count: counts?.re_examination,
    },
    { label: "Agency Code", to: `${BASE}/agency-code`, matchKey: "recruitment_leads", count: counts?.agency_code },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts } satisfies RecruitmentOutletContext} />
    </>
  );
}
