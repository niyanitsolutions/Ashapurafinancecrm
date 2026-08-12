import { Card, CardHeader } from "@/components/cards/Card";
import { NoDataState } from "@/components/charts/NoDataState";
import type { Widget } from "@/features/dashboard/api";
import { widgetData } from "@/features/dashboard/useDashboardWidgets";
import { Icon, type IconName } from "@/theme/icons";

function iconForEvent(eventType: string): IconName {
  if (eventType.includes("lead")) return "leads";
  if (eventType.includes("customer")) return "customers";
  if (eventType.includes("loan")) return "loan";
  if (eventType.includes("insurance") || eventType.includes("polic")) return "insurance";
  if (eventType.includes("task")) return "tasks";
  if (eventType.includes("application")) return "applications";
  if (eventType.includes("referral") || eventType.includes("commission")) return "referral";
  if (eventType.includes("document")) return "documents";
  return "clock";
}

function relativeTime(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2_592_000) return `${Math.floor(seconds / 86_400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

// recent_activities is minimal by design (event_type + created_at only, no actor name or
// linked entity — see dashboard redesign notes), so each row reads as a humanized event
// type + a relative timestamp rather than a fuller narrative the API doesn't provide.
// There's no company-wide activity log page to route a "View All" button to yet (the one
// "activity" route found is a per-employee placeholder), so it's omitted rather than
// linking somewhere that doesn't match.
export function RecentActivitiesCard({ widgets }: { widgets: Widget[] | undefined }) {
  const data = widgetData(widgets, "recent_activities");
  const items = Array.isArray(data?.items) ? (data!.items as { event_type: string; created_at: string | null }[]) : [];

  return (
    <Card>
      <CardHeader
        title="Recent Activities"
        icon={
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
            <Icon name="clock" className="h-4 w-4" />
          </span>
        }
      />
      {items.length === 0 ? (
        <NoDataState icon="clock" />
      ) : (
        <ul className="max-h-80 space-y-1 overflow-y-auto pr-1">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-3 rounded-lg px-1 py-2.5 hover:bg-background transition-colors">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Icon name={iconForEvent(item.event_type)} className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-text capitalize truncate">{item.event_type.replace(/_/g, " ")}</p>
                {item.created_at && <p className="text-2xs text-textSecondary">{relativeTime(item.created_at)}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
