import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { listOwnMessages, type MessageItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon, type IconName } from "@/theme/icons";

const STATUS_STYLE: Record<string, string> = {
  sent: "text-info",
  delivered: "text-success",
  failed: "text-danger",
  queued: "text-warning",
};
const STATUS_LABEL: Record<string, string> = { sent: "Sent", delivered: "Delivered", failed: "Failed", queued: "Sending…" };
const CHANNEL_ICON: Record<string, IconName> = { whatsapp: "chat", sms: "phone", email: "mail" };

// Customer Portal redesign — 3 buckets (Today/Yesterday/Earlier) instead of 4, per the
// requested grouping; still purely a client-side reshaping of the same `sent_at`/
// `created_at` fields, no backend change.
function dateBucket(iso: string, now: Date): string {
  const date = new Date(iso);
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const daysAgo = Math.floor((startOfDay(now).getTime() - startOfDay(date).getTime()) / 86_400_000);
  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  return "Earlier";
}

function groupByDate(messages: MessageItem[]): [string, MessageItem[]][] {
  const now = new Date();
  const order = ["Today", "Yesterday", "Earlier"];
  const groups = new Map<string, MessageItem[]>();
  for (const m of messages) {
    const bucket = dateBucket(m.sent_at ?? m.created_at, now);
    if (!groups.has(bucket)) groups.set(bucket, []);
    groups.get(bucket)!.push(m);
  }
  return order.filter((b) => groups.has(b)).map((b) => [b, groups.get(b)!]);
}

// Phase 5 (restyled as a notification/activity feed in the Customer Portal redesign) —
// Messages & Notifications. Both nav entries render this same read-only history:
// nothing in this CRM sends an internal, repliable "message" to a Customer today — every
// real update (documents requested, application submitted, etc.) already goes through
// Module 9C's Communication History (WhatsApp/SMS/Email), a one-way outbound delivery
// log. This is deliberately styled as a feed, not chat bubbles — there's no reply
// capability, attachments, or read-tracking to be honest about.
export function MessagesPage() {
  const [messages, setMessages] = useState<MessageItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    listOwnMessages()
      .then(setMessages)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  return (
    <SimplePageLayout title="Messages & Notifications" backTo="/portal">
      <ErrorBanner message={error} />
      {error && (
        <button type="button" onClick={load} className="mb-4 text-sm font-medium text-primary hover:underline">
          Try Again
        </button>
      )}

      {messages === null && !error && (
        <div className="max-w-2xl space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="animate-shimmer h-16 rounded-lg bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
          ))}
        </div>
      )}

      {messages !== null && messages.length === 0 && (
        <div className="bg-card border border-border rounded-card shadow-card p-10 text-center max-w-2xl">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Icon name="bell" className="h-6 w-6" />
          </span>
          <p className="text-sm font-medium text-text mb-1">No Messages Yet</p>
          <p className="text-sm text-text/50">Updates about your application will show up here.</p>
        </div>
      )}

      <div className="max-w-2xl space-y-5">
        {groupByDate(messages ?? []).map(([bucket, items]) => (
          <div key={bucket}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text/40 mb-2">{bucket}</h3>
            <div className="space-y-2">
              {items.map((m, i) => (
                <div key={i} className="bg-card border border-border rounded-card shadow-card p-4 flex gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Icon name={CHANNEL_ICON[m.channel] ?? "bell"} className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-sm font-medium text-text truncate">{m.subject || m.template_name || "Update"}</span>
                      <span className={`text-xs font-medium shrink-0 ${STATUS_STYLE[m.status] ?? "text-text/40"}`}>{STATUS_LABEL[m.status] ?? m.status}</span>
                    </div>
                    {m.body && <p className="text-sm text-text/70 whitespace-pre-wrap">{m.body}</p>}
                    <p className="text-xs text-text/40 mt-1 uppercase tracking-wide">
                      {m.channel} · {new Date(m.sent_at ?? m.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}
