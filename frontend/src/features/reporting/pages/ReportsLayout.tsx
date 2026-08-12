import { Outlet } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";

const TABS = [
  { label: "Reports", to: "/reports", matchKey: "reports" },
  { label: "Automated Reports", to: "/scheduled-reports", matchKey: "scheduled_reports" },
];

export function ReportsLayout() {
  return (
    <>
      <ModuleTabs tabs={TABS} />
      <Outlet />
    </>
  );
}
