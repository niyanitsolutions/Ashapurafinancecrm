import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { usePermissions } from "@/features/access_control/usePermissions";
import { BulkMessagesSection } from "@/features/communication/components/BulkMessagesSection";
import {
  createTemplate,
  listHistory,
  listQueue,
  listTemplates,
  retryQueueItem,
  updateTemplate,
  type CommunicationTemplate,
  type HistoryItem,
  type ProviderTemplateFields,
  type QueueItem,
} from "@/features/communication/api";
import { getErrorMessage } from "@/features/customer/errors";

const CHANNELS = ["whatsapp", "sms", "email"];
const CATEGORIES = ["otp", "welcome", "lead_assigned", "reminder", "application_submitted", "document_request", "commission_approved"];
const QUEUE_STATUSES = ["pending", "processing", "sent", "delivered", "failed", "retrying", "exhausted"];
const PAGE_SIZE = 20;

type Tab = "templates" | "queue" | "history" | "bulk";

const VALID_TABS: Tab[] = ["templates", "queue", "history", "bulk"];

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
        {(["templates", "queue", "history", "bulk"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t ? "border-primary text-primary" : "border-transparent text-text/60"}`}
          >
            {t === "templates" ? "Templates" : t === "queue" ? "Queue & Failed Messages" : t === "history" ? "Delivery History" : "Bulk Messages"}
          </button>
        ))}
      </div>

      {tab === "templates" && <TemplatesSection run={run} />}
      {tab === "queue" && <QueueSection run={run} />}
      {tab === "history" && <HistorySection />}
      {tab === "bulk" && <BulkMessagesSection run={run} />}
    </SimplePageLayout>
  );
}

function TemplatesSection({ run }: { run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void }) {
  const { can } = usePermissions();
  const canCreate = can("communication:templates", "create");
  const canEdit = can("communication:templates", "edit");
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Channels</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
          ))}
        </select>
        {canCreate && (
          <div className="sm:ml-auto">
            <Button size="sm" onClick={() => { setEditing(null); setShowForm(true); }}>
              + New Template
            </Button>
          </div>
        )}
      </div>

      {showForm && (
        <Modal open onClose={() => { setShowForm(false); setEditing(null); }} title={editing ? `Edit "${editing.name}"` : "New Template"} size="lg">
          <TemplateForm
            initial={editing}
            onSubmit={(payload) => {
              if (editing) {
                run(() => updateTemplate(editing.id, payload), "Template updated.", () => { setShowForm(false); setEditing(null); load(); });
              } else {
                run(() => createTemplate(payload as { name: string; channel: string; category: string; subject?: string; body: string } & ProviderTemplateFields), "Template created.", () => { setShowForm(false); load(); });
              }
            }}
          />
        </Modal>
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
                    primaryAction={canCreate ? { label: "New Template", onClick: () => setShowForm(true) } : undefined}
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
                  {canEdit && (
                    <button type="button" onClick={() => { setEditing(t); setShowForm(true); }} className="text-primary hover:underline text-xs">
                      Edit
                    </button>
                  )}
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
  onSubmit: (payload: { name?: string; channel?: string; category?: string; subject?: string; body: string } & ProviderTemplateFields) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [channel, setChannel] = useState(initial?.channel ?? CHANNELS[0]);
  const [category, setCategory] = useState(initial?.category ?? CATEGORIES[0]);
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [providerTemplateName, setProviderTemplateName] = useState(initial?.provider_template_name ?? "");
  const [providerTemplateNamespace, setProviderTemplateNamespace] = useState(initial?.provider_template_namespace ?? "");
  const [providerTemplateLanguage, setProviderTemplateLanguage] = useState(initial?.provider_template_language ?? "en");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const providerFields: ProviderTemplateFields =
          channel === "whatsapp"
            ? {
                provider_template_name: providerTemplateName || undefined,
                provider_template_namespace: providerTemplateNamespace || undefined,
                provider_template_language: providerTemplateLanguage || undefined,
              }
            : {};
        onSubmit(
          initial
            ? { body, subject: subject || undefined, ...providerFields }
            : { name, channel, category, subject: subject || undefined, body, ...providerFields },
        );
      }}
      className="space-y-3"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
      {channel === "whatsapp" && (
        <div className="rounded border border-border p-3 space-y-2">
          <p className="text-xs text-text/60">
            WhatsApp sends only a pre-approved provider template (not the body text above) — fill these in if using MSG91. The
            {"{{variable_name}}"} order above becomes the template's placeholder order.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <input
              placeholder="Provider Template Name" value={providerTemplateName}
              onChange={(e) => setProviderTemplateName(e.target.value)} className="rounded border border-border px-3 py-2 text-sm"
            />
            <input
              placeholder="Namespace" value={providerTemplateNamespace}
              onChange={(e) => setProviderTemplateNamespace(e.target.value)} className="rounded border border-border px-3 py-2 text-sm"
            />
            <input
              placeholder="Language code (e.g. en)" value={providerTemplateLanguage}
              onChange={(e) => setProviderTemplateLanguage(e.target.value)} className="rounded border border-border px-3 py-2 text-sm"
            />
          </div>
        </div>
      )}
      <SubmitButton>{initial ? "Save Changes" : "Create Template"}</SubmitButton>
    </form>
  );
}

function QueueSection({ run }: { run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void }) {
  const { can } = usePermissions();
  const canRetry = can("communication:queue", "edit");
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          {QUEUE_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={channelFilter} onChange={(e) => { setPage(1); setChannelFilter(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
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
                  {canRetry && (item.status === "failed" || item.status === "exhausted") && (
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
      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="messages" onPageChange={setPage} />
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          {QUEUE_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={channelFilter} onChange={(e) => { setPage(1); setChannelFilter(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
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
      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="records" onPageChange={setPage} />
    </div>
  );
}
