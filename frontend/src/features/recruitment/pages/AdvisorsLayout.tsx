import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getAdvisorCounts } from "@/features/recruitment/api";

const COUNT_POLL_INTERVAL_MS = 15_000;
const BASE = "/insurance-management/advisors";

export interface AdvisorOutletContext {
  refreshCounts: () => void;
}

export function AdvisorsLayout() {
  const [counts, setCounts] = useState<{ qr: number; non_qr: number } | null>(null);

  const loadCounts = useCallback(() => {
    // `qr` / `non_qr` in the response are global regardless of the channel arg.
    getAdvisorCounts("non_qr")
      .then((c) => setCounts({ qr: c.qr, non_qr: c.non_qr }))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    loadCounts();
    const interval = window.setInterval(loadCounts, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [loadCounts]);

  const tabs = [
    { label: "QR", to: `${BASE}/qr`, matchKey: "recruitment_leads", count: counts?.qr },
    { label: "Non QR", to: `${BASE}/non-qr`, matchKey: "recruitment_leads", count: counts?.non_qr },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts } satisfies AdvisorOutletContext} />
    </>
  );
}
