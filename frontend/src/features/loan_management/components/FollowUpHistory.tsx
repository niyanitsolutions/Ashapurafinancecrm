import { Badge } from "@/components/badges/Badge";
import type { CaseTimelineEntry } from "@/features/loan_management/api";
import { followUpTone, formatISTDate, formatISTDateTime } from "@/shared/dateFormat";

// Re-Eligible Case Management enhancement — the "Follow-up & Comment History" panel.
// Notes are grouped by their OWN `follow_up_date` into 🔴 Past / 🔵 Today / 🟢 Future and
// rendered strictly in that order; a note with no follow-up date lands in "Other History"
// (never mis-classified as Past/Today/Future). The colour is computed here at render time
// from the stored date — it is never sent to or stored on the server, so an entry moves
// from Today → Past on its own as the day rolls over.

type Group = "past" | "today" | "future" | "other";

const GROUP_META: Record<Group, { label: string; icon: string; tone: "danger" | "info" | "success" | "neutral" }> = {
  past: { label: "Past", icon: "🔴", tone: "danger" },
  today: { label: "Today", icon: "🔵", tone: "info" },
  future: { label: "Future", icon: "🟢", tone: "success" },
  other: { label: "Other History", icon: "•", tone: "neutral" },
};
const GROUP_ORDER: Group[] = ["past", "today", "future", "other"];

function groupOf(entry: CaseTimelineEntry): Group {
  if (!entry.follow_up_date) return "other";
  const tone = followUpTone(entry.follow_up_date);
  return tone === "danger" ? "past" : tone === "info" ? "today" : "future";
}

export function FollowUpHistory({ entries }: { entries: CaseTimelineEntry[] }) {
  const notes = entries.filter((e) => e.type === "note");

  if (notes.length === 0) {
    return <p className="text-sm text-text/40">No comments yet.</p>;
  }

  const buckets: Record<Group, CaseTimelineEntry[]> = { past: [], today: [], future: [], other: [] };
  for (const n of notes) buckets[groupOf(n)].push(n);

  for (const g of GROUP_ORDER) {
    buckets[g].sort((a, b) => {
      if (g === "other") return b.created_at.localeCompare(a.created_at); // newest first
      // Past/Today/Future: by follow-up date ascending, then created_at as the deterministic tiebreak.
      const byDate = (a.follow_up_date ?? "").localeCompare(b.follow_up_date ?? "");
      return byDate !== 0 ? byDate : a.created_at.localeCompare(b.created_at);
    });
  }

  return (
    <div className="space-y-4">
      {GROUP_ORDER.filter((g) => buckets[g].length > 0).map((g) => {
        const meta = GROUP_META[g];
        return (
          <div key={g}>
            <div className="mb-2 flex items-center gap-2">
              <span aria-hidden>{meta.icon}</span>
              <span className="text-xs font-semibold uppercase tracking-wide text-textSecondary">{meta.label}</span>
            </div>
            <div className="space-y-2">
              {buckets[g].map((n, i) => (
                <div key={`${g}-${i}`} className="rounded-lg border border-border bg-background px-3 py-2">
                  {n.follow_up_date && (
                    <Badge tone={meta.tone === "neutral" ? "info" : meta.tone}>{formatISTDate(n.follow_up_date)}</Badge>
                  )}
                  <div className="mt-1 text-sm text-text">{n.text}</div>
                  <div className="mt-0.5 text-2xs text-textSecondary">
                    {n.created_by ? `${n.created_by} · ` : ""}
                    {formatISTDateTime(n.created_at)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
