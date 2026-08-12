import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Insurance Cases", to: "/insurance-management/cases" },
  { label: "Policies Issued", to: "/insurance-management/policies-issued" },
  { label: "Re-Eligible", to: "/insurance-management/re-eligible" },
  { label: "Rejected", to: "/insurance-management/rejected" },
];

export function InsuranceManagementLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
