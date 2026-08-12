import { Icon, type IconName } from "@/theme/icons";

// Shared placeholder for any chart/card slot whose backing widget has no real data yet —
// "Never hardcode values"/"show No Data Available" per the dashboard redesign brief. Sized
// to hold a chart card's usual body height so the surrounding grid doesn't jump.
export function NoDataState({ icon = "grid", message = "No data available" }: { icon?: IconName; message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-textSecondary">
      <Icon name={icon} className="h-8 w-8 opacity-40" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
