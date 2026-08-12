import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  createTemplate,
  listHistory,
  listQueue,
  listTemplates,
  retryQueueItem,
  updateTemplate,
  type CommunicationTemplate,
  type HistoryItem,
  type QueueItem,
} from "@/features/communication/api";
import { getErrorMessage } from "@/features/customer/errors";

const CHANNELS = ["whatsapp", "sms", "email"];
const CATEGORIES = ["otp", "welcome", "lead_assigned", "reminder", "application_submitted", "document_request", "commission_approved"];
const QUEUE_STATUSES = ["pending", "processing", "sent", "delivered", "failed", "retrying", "exhausted"];
const PAGE_SIZE = 20;

type Tab = "templates" | "queue" | "history";

const VALID_TABS: Tab[] = ["templates", "queue", "history"];

export function CommunicationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab");
  const [tab, setTabState] = useState<Tab>(VALID_TABS.includes(initialTab as Tab) ? (initialTab as Tab) : "templates");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Keeps the URL (and so the sidebar's active-item highlighting) in sync with the
  // selected tab — deep-linkable from /communication?tab=queue etc.
  const setTab = (next: Tab) => {
    setTabState(next);
    setSearchParams({ tab: next }, { replace: true });
  };

  const run = async (action: () => Promise<unknown>, successMessage: string, after?: () => void) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      after?.();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="Message Center"
      subtitle="Automated WhatsApp, SMS, and Email messages your customers and partners receive — lead assignment, reminders, application updates, and commission approvals."
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 flex gap-2 border-b border-border">
        {(["templates", "queue", "history"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t ? "border-primary text-primary" : "border-transparent text-text/60"}`}
          >
            {t === "templates" ? "Templates" : t === "queue" ? "Queue & Failed Messages" : "Delivery History"}
          </button>
        ))}
      </div>

      {tab === "templates" && <TemplatesSection run={run} />}
      {tab === "queue" && <QueueSection run={run} />}
      {tab === "history" && <HistorySection />}
    </SimplePageLayout>
  );
}

function TemplatesSection({ run }: { run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void }) {
  const [templates, setTemplates] = useState<CommunicationTemplate[]>([]);
  const [channelFilter, setChannelFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<CommunicationTemplate | null>(null);

  const load = () => {
    listTemplates({ channel: channelFilter || undefined, category: categoryFilter || undefined }).then(setTemplates).catch(() => setTemplates([]));
  };

  useEffect(load, [channelFilter, categoryFilter]);

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <select value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Channels</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
          ))}
        </select>
        <button type="button" onClick={() => { setEditing(null); setShowForm((v) => !v); }} className="ml-auto rounded bg-primary text-white text-sm font-medium py-2 px-4">
          {showForm && !editing ? "Cancel" : "New Template"}
        </button>
      </div>

      {showForm && (
        <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-text/70 mb-3">{editing ? `Edit "${editing.name}"` : "New Template"}</h3>
          <TemplateForm
            initial={editing}
            onSubmit={(payload) => {
              if (editing) {
                run(() => updateTemplate(editing.id, payload), "Template updated.", () => { setShowForm(false); setEditing(null); load(); });
              } else {
                run(() => createTemplate(payload as { name: string; channel: string; category: string; subject?: string; body: string }), "Template created.", () => { setShowForm(false); load(); });
              }
            }}
          />
        </div>
      )}

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Channel</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Variables</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {templates.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon="communication"
                    title="No message templates yet"
                    description="Create a template for WhatsApp, SMS, or Email — it'll be used automatically the next time a matching event happens (e.g. a lead is assigned)."
                    primaryAction={{ label: "New Template", onClick: () => setShowForm(true) }}
                  />
                </td>
              </tr>
            )}
            {templates.map((t) => (
              <tr key={t.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{t.name}</td>
                <td className="px-4 py-3">{t.channel}</td>
                <td className="px-4 py-3 capitalize">{t.category.replace(/_/g, " ")}</td>
                <td className="px-4 py-3 text-xs text-text/60">{t.variables.join(", ") || "—"}</td>
                <td className="px-4 py-3 capitalize">{t.status}</td>
                <td className="px-4 py-3">
                  <button type="button" onClick={() => { setEditing(t); setShowForm(true); }} className="text-primary hover:underline text-xs">
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TemplateForm({
  initial, onSubmit,
}: {
  initial: CommunicationTemplate | null;
  onSubmit: (payload: { name?: string; channel?: string; category?: string; subject?: string; body: string }) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [channel, setChannel] = useState(initial?.channel ?? CHANNELS[0]);
  const [category, setCategory] = useState(initial?.category ?? CATEGORIES[0]);
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [body, setBody] = useState(initial?.body ?? "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(initial ? { body, subject: subject || undefined } : { name, channel, category, subject: subject || undefined, body });
      }}
      className="space-y-3"
    >
      <div className="grid grid-cols-3 gap-3">
        <input placeholder="Template Name" value={name} onChange={(e) => setName(e.target.value)} disabled={!!initial} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-60" required />
        <select value={channel} onChange={(e) => setChannel(e.target.value)} disabled={!!initial} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-60">
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={!!initial} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-60">
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
          ))}
        </select>
      </div>
      {channel === "email" && (
        <input placeholder="Subject (email only)" value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full rounded border border-border px-3 py-2 text-sm" />
      )}
      <textarea
        placeholder="Body — use {{variable_name}} for placeholders"
        value={body} onChange={(e) => setBody(e.target.value)} rows={4}
        className="w-full rounded border border-border px-3 py-2 text-sm font-mono"
        required
      />
      <SubmitButton>{initial ? "Save Changes" : "Create Template"}</SubmitButton>
    </form>
  );
}

function QueueSection({ run }: { run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void }) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");

  const load = () => {
    listQueue({ page, page_size: PAGE_SIZE, status: statusFilter || undefined, channel: channelFilter || undefined }).then((res) => {
      setItems(res.data);
      setTotal(res.pagination?.total ?? res.data.length);
    });
  };

  useEffect(load, [page, statusFilter, channelFilter]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <select value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {QUEUE_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={channelFilter} onChange={(e) => { setPage(1); setChannelFilter(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Channels</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Recipient</th>
              <th className="px-4 py-3">Channel</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Retries</th>
              <th className="px-4 py-3">Error</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon="communication"
                    title="No messages queued"
                    description="Messages are queued automatically by business events (like a lead being assigned) once a matching template exists."
                  />
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{item.recipient}</td>
                <td className="px-4 py-3">{item.channel}</td>
                <td className="px-4 py-3 capitalize">{item.status}</td>
                <td className="px-4 py-3">{item.retry_count}</td>
                <td className="px-4 py-3 max-w-xs truncate" title={item.error_detail || ""}>{item.error_detail || "—"}</td>
                <td className="px-4 py-3">{new Date(item.created_at).toLocaleString()}</td>
                <td className="px-4 py-3">
                  {(item.status === "failed" || item.status === "exhausted") && (
                    <button type="button" onClick={() => run(() => retryQueueItem(item.id), "Retry attempted.", load)} className="text-primary hover:underline text-xs">
                      Retry Now
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} messages)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}

function HistorySection() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");

  const load = () => {
    listHistory({ page, page_size: PAGE_SIZE, status: statusFilter || undefined, channel: channelFilter || undefined }).then((res) => {
      setItems(res.data);
      setTotal(res.pagination?.total ?? res.data.length);
    });
  };

  useEffect(load, [page, statusFilter, channelFilter]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <select value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {QUEUE_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={channelFilter} onChange={(e) => { setPage(1); setChannelFilter(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Channels</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Recipient</th>
              <th className="px-4 py-3">Channel</th>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">Template</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Retries</th>
              <th className="px-4 py-3">Sent</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState icon="communication" title="No delivery history yet" description="Sent, failed, and retried messages will show up here once your first message goes out." />
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{item.recipient}</td>
                <td className="px-4 py-3">{item.channel}</td>
                <td className="px-4 py-3">{item.provider}</td>
                <td className="px-4 py-3">{item.template_name}</td>
                <td className="px-4 py-3 capitalize">{item.status}</td>
                <td className="px-4 py-3">{item.retry_count}</td>
                <td className="px-4 py-3">{item.sent_at ? new Date(item.sent_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} records)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}
