import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Employee List", to: "/employees", matchKey: "employees", exact: true },
  { label: "Add Employee", to: "/employees/new", matchKey: "employees" },
  { label: "Documents", to: "/employees/documents", matchKey: "employees" },
  { label: "Employee Activity", to: "/employees/activity", matchKey: "employees" },
];

export function EmployeesLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
