import { useQuery } from "@tanstack/react-query";
import { getDashboard, type Widget } from "@/features/dashboard/api";

const MIN_REFRESH_SECONDS = 30;

// Same single `/dashboard` catalog call the page always made, now behind React Query so
// it's cached/deduped and auto-refetches at the shortest of the still-visible widgets'
// configured intervals (min 30s) — the same cadence rule the old manual setInterval used.
export function useDashboardWidgets() {
  return useQuery({
    queryKey: ["dashboard-widgets"],
    queryFn: getDashboard,
    staleTime: 30_000,
    refetchInterval: (query) => {
      const widgets = query.state.data;
      if (!widgets || widgets.length === 0) return false;
      const visible = widgets.filter((w) => w.is_visible);
      if (visible.length === 0) return false;
      const shortest = Math.min(...visible.map((w) => w.refresh_interval_seconds));
      return Math.max(shortest, MIN_REFRESH_SECONDS) * 1000;
    },
  });
}

export function findWidget(widgets: Widget[] | undefined, key: string): Widget | undefined {
  return widgets?.find((w) => w.key === key);
}

/** A widget's `data`, or `null` if the widget is missing, hidden (Customize), still
 * loading, or the provider itself reported `available: false` — one check every card uses
 * to decide between its real content and <NoDataState/>. */
export function widgetData(widgets: Widget[] | undefined, key: string): Record<string, unknown> | null {
  const widget = findWidget(widgets, key);
  if (!widget || !widget.is_visible || !widget.data) return null;
  if (widget.data.available === false) return null;
  return widget.data;
}
