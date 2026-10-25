import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ModuleTabs } from "@/components/layout/ModuleTabs";
import { usePermissions } from "@/features/access_control/usePermissions";
import { DAILY_UPDATE_TABS, permittedDailyUpdateTabs } from "./navigation";

export function DailyUpdateLayout() {
  const { can, loading } = usePermissions();
  const { pathname, search, hash } = useLocation();
  if (loading) return <p role="status" className="p-6">Loading Daily Update permissions…</p>;

  const tabs = permittedDailyUpdateTabs(can);
  if (pathname.replace(/\/$/, "") === "/daily-operations" && tabs.length) {
    return <Navigate to={`${tabs[0].to}${search}${hash}`} replace />;
  }
  const selected = DAILY_UPDATE_TABS.find((tab) => pathname === tab.to || pathname.startsWith(`${tab.to}/`));
  const permitted = selected && tabs.some((tab) => tab.to === selected.to);

  return (
    <section aria-label="Daily Update">
      <ModuleTabs tabs={tabs} ariaLabel="Daily Update tabs" />
      {permitted ? <Outlet /> : <p role="alert" className="p-6">You do not have permission to access this Daily Update page.</p>}
    </section>
  );
}
