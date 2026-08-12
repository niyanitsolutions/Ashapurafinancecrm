import { useEffect, useState } from "react";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  archiveNotification,
  dismissNotification,
  listNotifications,
  markNotificationRead,
  type AppNotification,
} from "@/features/reminders/api";

const PAGE_SIZE = 20;
// Same rationale as LeadListPage's poll — no push transport exists in this project yet,
// so a short background poll is how a newly-created notification (e.g. a Meta lead
// assignment) shows up without the user pressing refresh.
const POLL_INTERVAL_MS = 15_000;

const CATEGORIES = [
  { value: "assignment", label: "Assignment" },
  { value: "reminder", label: "Reminder" },
  { value: "task", label: "Task" },
  { value: "workflow", label: "Workflow" },
  { value: "document", label: "Document" },
  { value: "system", label: "System" },
  { value: "security", label: "Security" },
];

export function NotificationListPage() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setIsLoading(true);
    listNotifications({ page, page_size: PAGE_SIZE, status: status || undefined, category: category || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => {
        if (!opts.silent) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!opts.silent) setIsLoading(false);
      });
  };

  useEffect(load, [page, status, category]);

  useEffect(() => {
    if (page !== 1 || status || category) return;
    const interval = window.setInterval(() => load({ silent: true }), POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, status, category]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Notifications">
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      <div className="mb-4 flex items-center gap-4">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All</option>
          <option value="unread">Unread</option>
          <option value="read">Read</option>
          <option value="archived">Archived</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select value={category} onChange={(e) => { setPage(1); setCategory(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        {isLoading && <p className="text-sm text-text/50">Loading…</p>}
        {!isLoading && items.length === 0 && <p className="text-sm text-text/50">No notifications.</p>}
        {items.map((n) => (
          <div key={n.id} className={`bg-card border border-border rounded-card shadow-card p-4 ${n.status === "unread" ? "border-l-4 border-l-primary" : ""}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-text">{n.title}</span>
                  <span className="text-[10px] uppercase tracking-wide text-text/40 border border-border rounded px-1.5 py-0.5">{n.category}</span>
                </div>
                <div className="text-sm text-text/70">{n.message}</div>
                <div className="text-xs text-text/40 mt-1">{new Date(n.created_at).toLocaleString()}</div>
              </div>
              <div className="flex gap-2 shrink-0">
                {n.status === "unread" && (
                  <button type="button" onClick={() => run(() => markNotificationRead(n.id))} className="text-xs text-primary hover:underline">Mark Read</button>
                )}
                {n.status !== "archived" && (
                  <button type="button" onClick={() => run(() => archiveNotification(n.id))} className="text-xs text-text/60 hover:underline">Archive</button>
                )}
                {n.status !== "dismissed" && (
                  <button type="button" onClick={() => run(() => dismissNotification(n.id))} className="text-xs text-danger hover:underline">Dismiss</button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} notifications)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}
