import { Outlet, useLocation } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

// Insurance Management now hosts two distinct workflows: the existing policy-case
// pipeline ("Policy Leads") and Advisor Recruitment ("Recruitment Leads"). The top
// strip switches between them; the policy sub-tabs render underneath only while a
// Policy Leads route is open (Recruitment renders its own sub-tabs).
const TOP_TABS = [
  { label: "Recruitment Leads", to: "/insurance-management/recruitment", matchKey: "recruitment_leads" },
  {
    label: "Policy Leads",
    to: "/insurance-management/cases",
    matchKey: "insurance_cases",
    activePrefixes: [
      "/insurance-management/cases",
      "/insurance-management/policies-issued",
      "/insurance-management/re-eligible",
      "/insurance-management/rejected",
    ],
  },
  {
    label: "Advisors",
    to: "/insurance-management/advisors",
    matchKey: "recruitment_leads",
    activePrefixes: ["/insurance-management/advisors"],
  },
];

const POLICY_TABS = [
  { label: "Insurance Cases", to: "/insurance-management/cases" },
  { label: "Policies Issued", to: "/insurance-management/policies-issued" },
  { label: "Re-Eligible", to: "/insurance-management/re-eligible" },
  { label: "Rejected", to: "/insurance-management/rejected" },
];

export function InsuranceManagementLayout() {
  const { pathname } = useLocation();
  const onOwnSubTabs =
    pathname.startsWith("/insurance-management/recruitment") || pathname.startsWith("/insurance-management/advisors");
  return (
    <>
      <ModuleTabs tabs={TOP_TABS} />
      {!onOwnSubTabs && <ModuleTabs tabs={POLICY_TABS} />}
      <Outlet />
    </>
  );
}
