import { Card } from "@/components/cards/Card";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon, type IconName } from "@/theme/icons";

function MiniStat({ icon, label, value }: { icon: IconName; label: string; value: string | number }) {
  return (
    <Card className="flex items-center gap-3">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <p className="text-xl font-bold text-text tabular-nums leading-tight">{value}</p>
        <p className="text-2xs text-textSecondary leading-snug">{label}</p>
      </div>
    </Card>
  );
}

// `tasks` (pending list) is capped at 10 by the backend provider (nearest-due first) —
// Pending/Overdue below are real counts derived from that same real, if capped, response;
// Completed comes from the uncapped `tasks_completed` counter. Total = Pending + Completed,
// a simple real sum (not fabricated), though it inherits the same 10-item cap as Pending.
export function TaskOverviewRow({ widgets }: { widgets: Widget[] | undefined }) {
  const tasksData = widgetData(widgets, "tasks");
  const completedData = widgetData(widgets, "tasks_completed");

  const pendingItems = Array.isArray(tasksData?.items) ? (tasksData!.items as { title: string; due_at: string | null }[]) : [];
  const pending = pendingItems.length;
  const overdue = pendingItems.filter((t) => t.due_at && new Date(t.due_at).getTime() < Date.now()).length;
  const completed = typeof completedData?.value === "number" ? completedData.value : null;
  const total = completed === null ? null : completed + pending;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
      <MiniStat icon="clock" label="Pending Tasks" value={pending} />
      <MiniStat icon="check-circle" label="Completed Tasks" value={completed ?? "—"} />
      <MiniStat icon="alert-triangle" label="Overdue Tasks" value={overdue} />
      <MiniStat icon="tasks" label="Total Tasks" value={total ?? "—"} />
    </div>
  );
}
