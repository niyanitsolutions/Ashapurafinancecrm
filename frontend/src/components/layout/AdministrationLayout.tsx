import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Employees", to: "/employees", matchKey: "employees" },
  { label: "Roles & Permissions", to: "/roles", matchKey: "roles" },
  { label: "Departments", to: "/settings/departments", matchKey: "employees" },
  { label: "Designations", to: "/settings/designations", matchKey: "employees" },
  { label: "Temporary Access", to: "/temporary-access", matchKey: "temporary_access" },
  { label: "Geo Exceptions", to: "/geo-exceptions", matchKey: "geo_exceptions" },
  { label: "Lead Capture Log", to: "/lead-capture", matchKey: "lead_capture" },
];

export function AdministrationLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
