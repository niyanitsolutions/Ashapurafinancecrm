import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { getLeadCounts, type LeadCounts } from "@/features/leads/api";

// 5-tab Leads pipeline (decision 125, Leads workflow redesign Phase 1) — replaces the
// prior "New Leads"/"Assigned Leads" split, which was only ever a client-side
// derivation from `assigned_to` presence, not a real stage concept. Counts are fetched
// once here (server-computed, same scoping the matching tab's list query uses — see
// LeadService.get_tab_counts) and refetched on the same interval LeadListPage polls on,
// so a badge never drifts far from what its tab actually shows.
const COUNT_POLL_INTERVAL_MS = 15_000;

export function LeadsLayout() {
  const [counts, setCounts] = useState<LeadCounts | null>(null);

  const loadCounts = () => {
    getLeadCounts()
      .then(setCounts)
      .catch(() => undefined);
  };

  useEffect(() => {
    loadCounts();
    const interval = window.setInterval(loadCounts, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  const tabs = [
    { label: "Fresh Leads", to: "/leads", matchKey: "leads", exact: true, count: counts?.fresh },
    { label: "My Leads", to: "/leads/my", matchKey: "leads", count: counts?.my_leads },
    { label: "Document Collection", to: "/leads/document-collection", matchKey: "leads", count: counts?.document_collection },
    { label: "Rejected", to: "/leads/rejected", matchKey: "leads", count: counts?.rejected },
    { label: "Assigned", to: "/leads/assigned", matchKey: "leads", count: counts?.assigned },
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts }} />
    </>
  );
}
