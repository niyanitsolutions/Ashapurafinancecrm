import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getLeadCounts, type LeadCounts } from "@/features/leads/api";
import { getLoanCaseCounts } from "@/features/loan_management/api";

// 5-tab Leads pipeline (decision 125, Leads workflow redesign Phase 1) — replaces the
// prior "New Leads"/"Assigned Leads" split, which was only ever a client-side
// derivation from `assigned_to` presence, not a real stage concept. Counts are fetched
// once here (server-computed, same scoping the matching tab's list query uses — see
// LeadService.get_tab_counts) and refetched on the same interval LeadListPage polls on,
// so a badge never drifts far from what its tab actually shows.
const COUNT_POLL_INTERVAL_MS = 15_000;

export function LeadsLayout() {
  const { can } = usePermissions();
  // Top Up Loan's own data/actions are entirely Loan Management's (same case list,
  // same permission) — only its tab moved here. Gated on the same
  // loan_management:applications:view permission the underlying API already
  // enforces, so this tab is never shown to someone who'd immediately get a 403 from
  // it; not a new permission, just reusing the existing check client-side too.
  const canViewTopUp = can("loan_management:applications", "view");
  const [counts, setCounts] = useState<LeadCounts | null>(null);
  const [topUpCount, setTopUpCount] = useState<number | undefined>(undefined);

  const loadCounts = () => {
    getLeadCounts()
      .then(setCounts)
      .catch(() => undefined);
    if (canViewTopUp) {
      // Reuses Loan Management's own existing counts endpoint verbatim for this one
      // badge — no change to Leads' own counts endpoint/business logic.
      getLoanCaseCounts()
        .then((c) => setTopUpCount(c.top_up_eligible))
        .catch(() => undefined);
    }
  };

  useEffect(() => {
    loadCounts();
    const interval = window.setInterval(loadCounts, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canViewTopUp]);

  const tabs = [
    { label: "Fresh Leads", to: "/leads", matchKey: "leads", exact: true, count: counts?.fresh },
    { label: "My Leads", to: "/leads/my", matchKey: "leads", count: counts?.my_leads },
    { label: "Document Collection", to: "/leads/document-collection", matchKey: "leads", count: counts?.document_collection },
    { label: "Rejected", to: "/leads/rejected", matchKey: "leads", count: counts?.rejected },
    { label: "Assigned", to: "/leads/assigned", matchKey: "leads", count: counts?.assigned },
    ...(canViewTopUp ? [{ label: "Top Up Loan", to: "/leads/top-up", matchKey: "leads", count: topUpCount }] : []),
  ];

  return (
    <>
      <ModuleTabs tabs={tabs} />
      <Outlet context={{ refreshCounts: loadCounts }} />
    </>
  );
}
