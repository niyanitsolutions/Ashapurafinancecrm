import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Loan Cases", to: "/loan-management/cases" },
  { label: "Disbursements", to: "/loan-management/disbursements" },
  { label: "Re-Eligible", to: "/loan-management/re-eligible" },
  { label: "Rejected", to: "/loan-management/rejected" },
];

export function LoanManagementLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
