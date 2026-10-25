import type { ModuleTab } from "@/components/layout/ModuleTabs";
import type { PermissionsApi } from "@/features/access_control/usePermissions";
import { areas, type Area } from "./api";

interface DailyUpdateTab extends ModuleTab {
  area?: Area;
}

export const DAILY_UPDATE_TABS: DailyUpdateTab[] = [
  ...Object.entries(areas).map(([area, label]) => ({
    area: area as Area,
    label,
    to: `/daily-operations/${area}`,
  })),
  { label: "Import & Export Centre", to: "/daily-operations/transfers" },
];

export function permittedDailyUpdateTabs(can: PermissionsApi["can"]): DailyUpdateTab[] {
  // These tabs use the server's effective permission grants, including its canonical
  // Owner bypass. ModuleTabs needs no extra nav-key gate after this filtering.
  return DAILY_UPDATE_TABS.filter((tab) => tab.area
    ? can(`daily_operations:${tab.area}`, "view")
    : Object.keys(areas).some((area) => can(`daily_operations:${area}`, "view")
      && (can(`daily_operations:${area}`, "import") || can(`daily_operations:${area}`, "export"))));
}
