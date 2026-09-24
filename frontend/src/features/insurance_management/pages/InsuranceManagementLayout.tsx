import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getInsuranceCaseCounts, type InsuranceCaseCounts } from "@/features/insurance_management/api";

// Insurance Management hosts three workflows: the "Policy Leads" pipeline, Advisor
// Recruitment ("Recruitment Leads"), and Advisor Management ("Advisors"). The top strip
// switches between them; the Policy Leads sub-tabs render underneath only while a Policy
// Leads route is open (Recruitment renders its own sub-tabs; Advisors is a single
// filtered list).
const POLICY_LEADS_PREFIXES = [
  "/insurance-management/fresh-leads",
  "/insurance-management/policy-document",
  "/insurance-management/policy-login",
  "/insurance-management/payment",
  "/insurance-management/policy-issued",
  "/insurance-management/re-eligible",
  "/insurance-management/rejected",
  "/insurance-management/on-hold",
];

const TOP_TABS = [
  {
    label: "Policy Leads",
    to: "/insurance-management/fresh-leads",
    matchKey: "insurance_cases",
    activePrefixes: POLICY_LEADS_PREFIXES,
  },
  // These are workflows within Insurance Management, not separately-entered modules.
  // An employee who can enter Insurance Management sees the complete navigation; each
  // workflow API then returns only the records/counts that employee may access.
  { label: "Recruitment Leads", to: "/insurance-management/recruitment", matchKey: "insurance_cases" },
  {
    label: "Advisors",
    to: "/insurance-management/advisors",
    matchKey: "insurance_cases",
    activePrefixes: ["/insurance-management/advisors"],
  },
];

const COUNT_POLL_INTERVAL_MS = 15_000;

export function InsuranceManagementLayout() {
  const { can } = usePermissions();
  const { pathname } = useLocation();
  const onPolicyLeads = POLICY_LEADS_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const [counts, setCounts] = useState<InsuranceCaseCounts | null>(null);

  useEffect(() => {
    if (!onPolicyLeads) return;
    const load = () => getInsuranceCaseCounts().then(setCounts).catch(() => undefined);
    load();
    const interval = window.setInterval(load, COUNT_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [onPolicyLeads]);

  // The pipeline stages, each with a live server-computed count badge, plus a link out to
  // the single source of truth for what each insurance product asks for (the
  // category-aware Product Schema Engine — no count).
  const policyTabs = [
    { key: "fresh_lead", label: "Fresh Leads", to: "/insurance-management/fresh-leads", count: counts?.fresh_lead },
    { key: "policy_document", label: "Policy Document", to: "/insurance-management/policy-document", count: counts?.policy_document },
    { key: "policy_login", label: "Policy Login", to: "/insurance-management/policy-login", count: counts?.policy_login },
    { key: "payment", label: "Payment", to: "/insurance-management/payment", count: counts?.payment },
    { key: "policy_issued", label: "Policy Issued", to: "/insurance-management/policy-issued", count: counts?.policy_issued },
    { key: "re_eligible", label: "Re-Eligible", to: "/insurance-management/re-eligible", count: counts?.re_eligible },
    { key: "rejected", label: "Rejected", to: "/insurance-management/rejected", count: counts?.rejected },
    { key: "on_hold", label: "On Hold", to: "/insurance-management/on-hold", count: counts?.on_hold },
    { key: "settings", label: "Settings", to: "/settings/product-schemas?category=insurance" },
  ].filter((tab) => can(`insurance_management:applications.${tab.key}`, "view"));

  const topTabs = TOP_TABS.filter((tab) => {
    if (tab.label === "Policy Leads") {
      return can("insurance_management:applications", "view") || policyTabs.some((item) => item.key);
    }
    if (tab.label === "Recruitment Leads") {
      return can("insurance_management:recruitment", "view") || [
        "fresh", "bop", "doc_collection", "exam_fee_status", "examination",
        "re_examination", "agency_code", "rejected",
      ].some((stage) => can(`insurance_management:recruitment.${stage}`, "view"));
    }
    return can("insurance_management:advisors", "view");
  });

  return (
    <>
      <ModuleTabs tabs={topTabs} />
      {onPolicyLeads && <ModuleTabs tabs={policyTabs} />}
      <Outlet />
    </>
  );
}
