import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "New Leads", to: "/leads", matchKey: "leads", exact: true },
  { label: "Assigned Leads", to: "/leads/assigned", matchKey: "leads" },
];

export function LeadsLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
