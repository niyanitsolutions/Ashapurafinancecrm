import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Customers", to: "/customers", matchKey: "customers", exact: true },
  { label: "Customer Applications", to: "/applications", matchKey: "applications" },
];

export function CustomersLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
