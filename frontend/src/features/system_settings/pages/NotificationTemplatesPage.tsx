import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
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

export function NotificationTemplatesPage() {
  const [items, setItems] = useState<NotificationTemplate[]>([]);
  const [channelFilter, setChannelFilter] = useState("");
  const [newChannel, setNewChannel] = useState("");
  const [newKey, setNewKey] = useState("");
  const [newSubject, setNewSubject] = useState("");
  const [newBody, setNewBody] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    listNotificationTemplates(channelFilter.trim() || undefined)
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [channelFilter]);  

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newChannel.trim() || !newKey.trim() || !newBody.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await createNotificationTemplate({
        channel: newChannel.trim(),
        key: newKey.trim(),
        subject: newSubject.trim() || undefined,
        body: newBody,
      });
      setNewKey("");
      setNewSubject("");
      setNewBody("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

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
    <SimplePageLayout title="Notification Templates">
      <ErrorBanner message={error} />

      <div className="mb-4 max-w-xs">
        <FormField label="Filter by channel" value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} placeholder="e.g. sms" />
      </div>

      <form onSubmit={onCreate} className="mb-6 grid grid-cols-2 gap-3 max-w-2xl">
        <FormField label="Channel" value={newChannel} onChange={(e) => setNewChannel(e.target.value)} placeholder="e.g. sms / email / whatsapp" />
        <FormField label="Key" value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="e.g. otp_signup" />
        <FormField label="Subject (email only)" value={newSubject} onChange={(e) => setNewSubject(e.target.value)} />
        <div />
        <div className="col-span-2">
          <label className="block text-sm font-medium text-text mb-1">Body</label>
          <textarea
            className="w-full rounded border border-border px-3 py-2 text-sm"
            rows={3}
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            placeholder="Use {{variable}} placeholders"
          />
        </div>
        <div className="col-span-2">
          <SubmitButton isSubmitting={isSubmitting}>Add Template</SubmitButton>
        </div>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
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
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text/50">
                  No templates yet.
                </td>
              </tr>
            )}
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
    </SimplePageLayout>
  );
}
