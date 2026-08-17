import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getApplicationTimeline, type TimelineEntry } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon, type IconName } from "@/theme/icons";

const STATE_STYLES: Record<TimelineEntry["state"], string> = {
  completed: "bg-success text-white",
  current: "bg-primary text-white",
  upcoming: "bg-border text-text/40",
  rejected: "bg-danger text-white",
};
const STATE_ICON: Record<TimelineEntry["state"], IconName | null> = {
  completed: "check-circle",
  current: null,
  upcoming: null,
  rejected: "x-circle",
};

// Phase 5 (restyled in the Customer Portal redesign) — the visual application timeline.
// Stage labels/order/timestamps/actor names come straight from the backend's
// `GET /applications/{id}/timeline`, itself derived from real Lead/Application/Workflow
// Engine data (see docs — no stage or attribution is ever invented on either side).
export function ApplicationTimelinePage() {
  const { id } = useParams<{ id: string }>();
  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!id) return;
    setError(null);
    getApplicationTimeline(id)
      .then(setEntries)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [id]);

  return (
    <SimplePageLayout title="Application Timeline" backTo={id ? `/portal/applications/${id}` : "/portal"}>
      <ErrorBanner message={error} />
      {error && (
        <button type="button" onClick={load} className="mb-4 text-sm font-medium text-primary hover:underline">
          Try Again
        </button>
      )}
      {entries === null && !error && (
        <div className="max-w-2xl space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="animate-shimmer h-12 rounded-lg bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
          ))}
        </div>
      )}
      {entries && (
        <ol className="max-w-2xl">
          {entries.map((entry, i) => (
            <li key={i} className="relative pl-8 pb-8 last:pb-0 animate-fade-in" style={{ animationDelay: `${i * 60}ms` }}>
              {i < entries.length - 1 && <span className="absolute left-[11px] top-6 bottom-0 w-0.5 bg-border" />}
              <span
                className={`absolute left-0 top-0.5 flex h-6 w-6 items-center justify-center rounded-full transition-colors ${STATE_STYLES[entry.state]}`}
              >
                {STATE_ICON[entry.state] && <Icon name={STATE_ICON[entry.state] as IconName} className="h-3.5 w-3.5" />}
              </span>
              <p className={`text-sm font-medium ${entry.state === "upcoming" ? "text-text/40" : "text-text"}`}>{entry.label}</p>
              {entry.occurred_at && <p className="text-xs text-text/40">{formatISTDateTime(entry.occurred_at)}</p>}
              {entry.actor_name && <p className="text-xs text-text/50">by {entry.actor_name}</p>}
              {entry.state === "current" && <p className="text-xs text-primary font-medium">In progress</p>}
            </li>
          ))}
        </ol>
      )}
    </SimplePageLayout>
  );
}
