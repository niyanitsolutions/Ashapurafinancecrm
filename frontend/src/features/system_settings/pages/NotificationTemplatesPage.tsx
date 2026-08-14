import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  activateNotificationTemplate,
  createNotificationTemplate,
  deactivateNotificationTemplate,
  listNotificationTemplates,
  type NotificationTemplate,
  updateNotificationTemplate,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

const CHANNEL_OPTIONS = [
  { value: "internal", label: "Internal (in-app notifications)" },
  { value: "sms", label: "SMS" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
];

// Keys the Reminder & Notification Engine actually looks up when channel="internal" —
// see backend/app/features/reminders/constants.py's NotificationType. A template row
// with one of these keys overrides that event's default title/message; anything else is
// simply unused. Kept here as UI-only documentation, not enforced.
const INTERNAL_KEYS = [
  "task_assigned",
  "lead_assigned",
  "document_uploaded",
  "task_due",
  "task_escalation",
  "task_owner_escalation",
  "reminder_triggered",
  "support_request_raised",
];

interface TemplateFormState {
  channel: string;
  key: string;
  subject: string;
  body: string;
}

function TemplateFormModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<TemplateFormState>({ channel: "internal", key: "", subject: "", body: "" });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.channel.trim() || !form.key.trim() || !form.body.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await createNotificationTemplate({
        channel: form.channel.trim(),
        key: form.key.trim(),
        subject: form.subject.trim() || undefined,
        body: form.body,
      });
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Add Notification Template"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="notification-template-form" size="sm" loading={isSubmitting}>
            Add Template
          </Button>
        </>
      }
    >
      <form id="notification-template-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <SelectField
          label="Channel"
          value={form.channel}
          onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))}
          options={CHANNEL_OPTIONS}
        />
        <FormField
          label="Key"
          value={form.key}
          onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
          placeholder="e.g. otp_signup"
          required
        />
        {form.channel === "internal" && (
          <p className="-mt-3 mb-4 text-2xs text-textSecondary">
            Recognized keys: {INTERNAL_KEYS.join(", ")}. Any other key is stored but never used.
          </p>
        )}
        <FormField
          label="Subject / Title (optional)"
          value={form.subject}
          onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
        />
        <TextareaField
          label="Body"
          value={form.body}
          onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
          rows={3}
          placeholder="Use {{variable}} placeholders"
          required
        />
      </form>
    </Modal>
  );
}

export function NotificationTemplatesPage() {
  const [items, setItems] = useState<NotificationTemplate[]>([]);
  const [channelFilter, setChannelFilter] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const load = () => {
    listNotificationTemplates(channelFilter.trim() || undefined)
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [channelFilter]);

  const startEdit = (item: NotificationTemplate) => {
    setEditingId(item.id);
    setEditSubject(item.subject ?? "");
    setEditBody(item.body);
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await updateNotificationTemplate(id, { subject: editSubject.trim() || undefined, body: editBody });
      setEditingId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onToggleStatus = async (item: NotificationTemplate) => {
    setError(null);
    try {
      if (item.status === "active") await deactivateNotificationTemplate(item.id);
      else await activateNotificationTemplate(item.id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="Notification Templates"
      subtitle="Manage message templates for automated notifications."
      actions={<Button size="sm" onClick={() => setIsModalOpen(true)}>+ Add Template</Button>}
    >
      <ErrorBanner message={error} />

      <div className="mb-4 max-w-xs">
        <FormField label="Filter by channel" value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} placeholder="e.g. internal" />
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon="bell"
          title="No notification templates yet"
          description="Add a template to customize automated notification content."
          primaryAction={{ label: "+ Add Template", onClick: () => setIsModalOpen(true) }}
        />
      ) : (
        <div className="overflow-x-auto rounded-card border border-border bg-card shadow-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Channel</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Body</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) =>
                editingId === item.id ? (
                  <tr key={item.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2 text-text/60">{item.channel}</td>
                    <td className="px-4 py-2 text-text/60">{item.key}</td>
                    <td className="px-4 py-2">
                      <input
                        className="mb-1 w-full rounded border border-border px-2 py-1"
                        placeholder="Subject"
                        value={editSubject}
                        onChange={(e) => setEditSubject(e.target.value)}
                      />
                      <textarea
                        className="w-full rounded border border-border px-2 py-1"
                        rows={2}
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                      />
                    </td>
                    <td className="px-4 py-2 capitalize">{item.status}</td>
                    <td className="px-4 py-2 text-right space-x-2">
                      <button type="button" className="text-primary hover:underline" onClick={() => onSaveEdit(item.id)}>
                        Save
                      </button>
                      <button type="button" className="text-text/60 hover:underline" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </td>
                  </tr>
                ) : (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                    <td className="px-4 py-3">{item.channel}</td>
                    <td className="px-4 py-3">{item.key}</td>
                    <td className="px-4 py-3 max-w-md truncate" title={item.body}>
                      {item.body}
                    </td>
                    <td className="px-4 py-3 capitalize">{item.status}</td>
                    <td className="px-4 py-3 text-right space-x-3">
                      <button type="button" className="text-primary hover:underline" onClick={() => startEdit(item)}>
                        Edit
                      </button>
                      <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(item)}>
                        {item.status === "active" ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}

      {isModalOpen && (
        <TemplateFormModal
          onClose={() => setIsModalOpen(false)}
          onSaved={() => {
            setIsModalOpen(false);
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
