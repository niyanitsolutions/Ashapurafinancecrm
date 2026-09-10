import { Outlet, useLocation } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

// Insurance Management hosts three workflows: the "Policy Leads" pipeline, Advisor
// Recruitment ("Recruitment Leads"), and Advisor Management ("Advisors"). The top strip
// switches between them; the Policy Leads sub-tabs render underneath only while a Policy
// Leads route is open (Recruitment renders its own sub-tabs; Advisors is a single
// filtered list).
const POLICY_LEADS_PREFIXES = [
  "/insurance-management/fresh-leads",
  "/insurance-management/policy-document",
  "/insurance-management/policy-login",
  "/insurance-management/policy-issued",
  "/insurance-management/re-eligible",
  "/insurance-management/rejected",
];

const TOP_TABS = [
  {
    label: "Policy Leads",
    to: "/insurance-management/fresh-leads",
    matchKey: "insurance_cases",
    activePrefixes: POLICY_LEADS_PREFIXES,
  },
  { label: "Recruitment Leads", to: "/insurance-management/recruitment", matchKey: "recruitment_leads" },
  {
    label: "Advisors",
    to: "/insurance-management/advisors",
    matchKey: "recruitment_leads",
    activePrefixes: ["/insurance-management/advisors"],
  },
];

// The pipeline stages, plus a link out to the single source of truth for what each
// insurance product asks for (the category-aware Product Schema Engine).
const POLICY_TABS = [
  { label: "Fresh Leads", to: "/insurance-management/fresh-leads" },
  { label: "Policy Document", to: "/insurance-management/policy-document" },
  { label: "Policy Login", to: "/insurance-management/policy-login" },
  { label: "Policy Issued", to: "/insurance-management/policy-issued" },
  { label: "Re-Eligible", to: "/insurance-management/re-eligible" },
  { label: "Rejected", to: "/insurance-management/rejected" },
  { label: "Settings", to: "/settings/product-schemas?category=insurance" },
];

export function InsuranceManagementLayout() {
  const { pathname } = useLocation();
  const onPolicyLeads = POLICY_LEADS_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  return (
    <>
      <ModuleTabs tabs={TOP_TABS} />
      {onPolicyLeads && <ModuleTabs tabs={POLICY_TABS} />}
      <Outlet />
    </>
  );
}
