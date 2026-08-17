import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { EmptyState } from "@/components/layout/EmptyState";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { usePermissions } from "@/features/access_control/usePermissions";
import {
  cancelBulkMessageJob,
  createBulkMessageJob,
  getBulkMessageJob,
  listBulkMessageJobFailed,
  listBulkMessageJobs,
  listTemplates,
  retryBulkMessageJobFailed,
  type BulkMessageJobDetail,
  type BulkMessageJobListItem,
  type CommunicationTemplate,
  type CrmEntityType,
  type QueueItem,
} from "@/features/communication/api";
import { listCustomersStaff, type CustomerListItem } from "@/features/customer/api";
import { listLeads, type LeadListItem } from "@/features/leads/api";
import { getErrorMessage } from "@/shared/api/errors";
import { formatISTDateTime } from "@/shared/dateFormat";

const CHANNELS = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "sms", label: "SMS" },
  { value: "email", label: "Email" },
] as const;

const STATUS_LABEL: Record<string, string> = { queued: "Queued", processing: "Processing", completed: "Completed", cancelled: "Cancelled" };

type Recipient = { id: string; full_name: string; mobile: string; email: string | null };

export function BulkMessagesSection({ run }: { run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void }) {
  const { can } = usePermissions();
  const canCreate = can("communication:bulk", "create");
  const [showComposer, setShowComposer] = useState(false);
  const [jobs, setJobs] = useState<BulkMessageJobListItem[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const load = () => {
    listBulkMessageJobs({ page: 1, page_size: 20 }).then((r) => setJobs(r.data)).catch(() => setJobs([]));
  };

  useEffect(load, []);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text/60">Send one message to many Leads or Customers at once — queued through the same background delivery pipeline as every other message.</p>
        {canCreate && (
          <Button size="sm" onClick={() => setShowComposer(true)}>
            + New Bulk Message
          </Button>
        )}
      </div>

      {showComposer && (
        <BulkMessageComposer
          onClose={() => setShowComposer(false)}
          onCreated={() => {
            setShowComposer(false);
            load();
          }}
          run={run}
        />
      )}

      {jobs.length === 0 ? (
        <EmptyState icon="communication" title="No bulk messages yet" description="Send your first bulk message to a group of Leads or Customers." primaryAction={canCreate ? { label: "+ New Bulk Message", onClick: () => setShowComposer(true) } : undefined} />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Channel</th>
                <th className="px-4 py-3">Recipients</th>
                <th className="px-4 py-3">Queued</th>
                <th className="px-4 py-3">Skipped</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3">{formatISTDateTime(job.created_at)}</td>
                  <td className="px-4 py-3 capitalize">{job.channel}</td>
                  <td className="px-4 py-3">{job.recipient_count}</td>
                  <td className="px-4 py-3">{job.queued_count}</td>
                  <td className="px-4 py-3">{job.skipped_count}</td>
                  <td className="px-4 py-3">{STATUS_LABEL[job.status] ?? job.status}</td>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => setSelectedJobId(job.id)} className="text-primary hover:underline text-xs">
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJobId && (
        <BulkJobDetailPanel jobId={selectedJobId} onClose={() => setSelectedJobId(null)} run={run} onChanged={load} />
      )}
    </div>
  );
}

function BulkMessageComposer({
  onClose, onCreated, run,
}: {
  onClose: () => void;
  onCreated: () => void;
  run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void;
}) {
  const [channel, setChannel] = useState<string>("whatsapp");
  const [recipientType, setRecipientType] = useState<CrmEntityType>("lead");
  const [templates, setTemplates] = useState<CommunicationTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Recipient[]>([]);
  const [selected, setSelected] = useState<Map<string, Recipient>>(new Map());
  const [isSearching, setIsSearching] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setTemplateId("");
    listTemplates({ channel }).then((items) => setTemplates(items.filter((t) => t.status === "active"))).catch(() => setTemplates([]));
  }, [channel]);

  useEffect(() => {
    setResults([]);
  }, [recipientType]);

  const onSearch = async () => {
    setIsSearching(true);
    try {
      if (recipientType === "lead") {
        const r = await listLeads({ page: 1, page_size: 50, search: search || undefined });
        setResults(r.data.map((l: LeadListItem) => ({ id: l.id, full_name: l.full_name, mobile: l.mobile, email: l.email })));
      } else {
        const r = await listCustomersStaff({ page: 1, page_size: 50, search: search || undefined });
        setResults(r.data.map((c: CustomerListItem) => ({ id: c.id, full_name: c.full_name, mobile: c.mobile, email: c.email })));
      }
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const toggle = (recipient: Recipient) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(recipient.id)) next.delete(recipient.id);
      else next.set(recipient.id, recipient);
      return next;
    });
  };

  const onSubmit = () => {
    setIsSubmitting(true);
    run(
      () => createBulkMessageJob({ channel, template_id: templateId, recipient_type: recipientType, recipient_ids: Array.from(selected.keys()) }),
      `Bulk message queued for ${selected.size} recipient(s).`,
      onCreated,
    );
    setIsSubmitting(false);
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="New Bulk Message"
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!templateId || selected.size === 0} loading={isSubmitting} onClick={onSubmit}>
            Queue Bulk Message
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">Channel</label>
            <div className="flex gap-2">
              {CHANNELS.map((c) => (
                <button
                  key={c.value} type="button" onClick={() => setChannel(c.value)}
                  className={`flex-1 rounded-lg border py-2 text-sm font-medium ${channel === c.value ? "border-primary bg-primary/10 text-primary" : "border-border text-text/60"}`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">Template</label>
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} className="w-full rounded-lg border border-border px-3 py-2 text-sm">
              <option value="">Select a template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-text mb-1.5">Recipients</label>
          <div className="flex flex-wrap gap-3 mb-2">
            <select value={recipientType} onChange={(e) => setRecipientType(e.target.value as CrmEntityType)} className="rounded-lg border border-border px-3 py-2 text-sm">
              <option value="lead">Leads</option>
              <option value="customer">Customers</option>
            </select>
            <input
              value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name or mobile"
              className="flex-1 min-w-[160px] rounded-lg border border-border px-3 py-2 text-sm"
            />
            <Button variant="secondary" size="sm" disabled={isSearching} onClick={onSearch}>
              {isSearching ? "Searching…" : "Search"}
            </Button>
          </div>

          {results.length > 0 && (
            <div className="max-h-56 overflow-y-auto border border-border rounded-lg divide-y divide-border">
              {results.map((r) => (
                <label key={r.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-background">
                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r)} className="accent-primary" />
                  <span className="font-medium">{r.full_name}</span>
                  <span className="text-text/50 text-xs">{r.mobile}{r.email ? ` · ${r.email}` : ""}</span>
                </label>
              ))}
            </div>
          )}

          <p className="mt-2 text-sm text-text/60">
            Recipients selected: <span className="font-semibold text-text">{selected.size}</span>
          </p>
        </div>
      </div>
    </Modal>
  );
}

function BulkJobDetailPanel({
  jobId, onClose, run, onChanged,
}: {
  jobId: string;
  onClose: () => void;
  run: (action: () => Promise<unknown>, successMessage: string, after?: () => void) => void;
  onChanged: () => void;
}) {
  const { can } = usePermissions();
  const canEdit = can("communication:bulk", "edit");
  const [job, setJob] = useState<BulkMessageJobDetail | null>(null);
  const [failed, setFailed] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const load = () => {
    getBulkMessageJob(jobId).then(setJob).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [jobId]);

  const onViewFailed = () => {
    listBulkMessageJobFailed(jobId).then(setFailed).catch(() => setFailed([]));
  };

  return (
    <Modal open onClose={onClose} title="Bulk Send Result" footer={<Button size="sm" onClick={onClose}>Close</Button>}>
      {error && <p className="text-sm text-danger mb-2">{error}</p>}
      {job && (
        <>
          <div className="grid grid-cols-2 gap-3 text-sm mb-4 sm:grid-cols-3">
            <div><div className="text-text/50 text-xs">Total</div><div className="font-semibold">{job.recipient_count}</div></div>
            <div><div className="text-text/50 text-xs">Queued</div><div className="font-semibold">{job.queued_count}</div></div>
            <div><div className="text-text/50 text-xs">Skipped</div><div className="font-semibold">{job.skipped_count}</div></div>
            <div><div className="text-text/50 text-xs">Sent</div><div className="font-semibold text-primary">{job.sent}</div></div>
            <div><div className="text-text/50 text-xs">Delivered</div><div className="font-semibold text-success">{job.delivered}</div></div>
            <div><div className="text-text/50 text-xs">Failed</div><div className="font-semibold text-danger">{job.failed}</div></div>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            <Button variant="secondary" size="sm" onClick={onViewFailed}>
              View Failed
            </Button>
            {canEdit && job.failed > 0 && (
              <Button
                variant="secondary" size="sm"
                onClick={() => run(() => retryBulkMessageJobFailed(jobId), "Failed messages re-queued.", () => { load(); onChanged(); })}
              >
                Retry Failed
              </Button>
            )}
            {canEdit && (job.status === "queued" || job.status === "processing") && (
              <Button variant="danger" size="sm" onClick={() => setConfirmCancel(true)}>
                Cancel
              </Button>
            )}
          </div>

          {failed && (
            <div className="max-h-48 overflow-y-auto border border-border rounded-lg divide-y divide-border mb-4">
              {failed.length === 0 ? (
                <p className="px-3 py-3 text-sm text-text/50">No failed messages.</p>
              ) : (
                failed.map((item) => (
                  <div key={item.id} className="px-3 py-2 text-sm">
                    <div className="font-medium">{item.recipient}</div>
                    <div className="text-xs text-danger">{item.error_detail}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmCancel}
        title="Cancel Bulk Job"
        message="Cancel this bulk message job? Messages not yet queued will not be sent."
        confirmLabel="Cancel Job"
        confirmVariant="danger"
        onConfirm={() => {
          run(() => cancelBulkMessageJob(jobId), "Bulk job cancelled.", () => { load(); onChanged(); });
          setConfirmCancel(false);
        }}
        onClose={() => setConfirmCancel(false)}
      />
    </Modal>
  );
}
