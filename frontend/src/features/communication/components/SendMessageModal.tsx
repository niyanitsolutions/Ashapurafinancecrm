import { useEffect, useState } from "react";
import { listTemplates, sendCrmMessage, type CommunicationTemplate, type CrmEntityType } from "@/features/communication/api";
import { getErrorMessage } from "@/shared/api/errors";

const CHANNELS = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "sms", label: "SMS" },
  { value: "email", label: "Email" },
] as const;

// Auto-resolved server-side from the Lead/Customer record itself (see
// CommunicationService.send_crm_message) — never shown as a free-text input, since the
// recipient address must never be client-suppliable (IDOR/spoofing risk).
const AUTO_RESOLVED_VARIABLES = new Set(["customer_name", "mobile", "email"]);

export function SendMessageModal({
  entityType, entityId, entityLabel, onClose, onSent,
}: {
  entityType: CrmEntityType;
  entityId: string;
  entityLabel: string;
  onClose: () => void;
  onSent: () => void;
}) {
  const [channel, setChannel] = useState<string>("whatsapp");
  const [templates, setTemplates] = useState<CommunicationTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [extraVariables, setExtraVariables] = useState<Record<string, string>>({});
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ success: boolean; error: string | null } | null>(null);

  useEffect(() => {
    setIsLoadingTemplates(true);
    setTemplateId("");
    setResult(null);
    listTemplates({ channel })
      .then((items) => setTemplates(items.filter((t) => t.status === "active")))
      .catch(() => setTemplates([]))
      .finally(() => setIsLoadingTemplates(false));
  }, [channel]);

  const selectedTemplate = templates.find((t) => t.id === templateId) ?? null;
  const neededVariables = (selectedTemplate?.variables ?? []).filter((v) => !AUTO_RESOLVED_VARIABLES.has(v));

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setIsSubmitting(true);
    try {
      const outcome = await sendCrmMessage({ entity_type: entityType, entity_id: entityId, channel, template_id: templateId, variables: extraVariables });
      setResult({ success: outcome.success, error: outcome.error });
      if (outcome.success) onSent();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md bg-card border border-border rounded-2xl shadow-dropdown p-6">
        <h2 className="text-lg font-bold text-text mb-1">Send Message</h2>
        <p className="text-xs text-text/50 mb-4">{entityLabel}</p>

        {error && <p className="mb-3 text-sm text-danger">{error}</p>}
        {result && (
          <p className={`mb-3 text-sm ${result.success ? "text-success" : "text-danger"}`}>
            {result.success ? "✓ Message sent." : `✕ ${result.error || "Message could not be sent."}`}
          </p>
        )}

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">Channel</label>
            <div className="flex gap-2">
              {CHANNELS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setChannel(c.value)}
                  className={`flex-1 rounded-xl border py-2 text-sm font-medium transition-colors ${
                    channel === c.value ? "border-primary bg-primary/10 text-primary" : "border-border text-text/60 hover:bg-background"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1.5">Template</label>
            {isLoadingTemplates ? (
              <p className="text-xs text-text/50">Loading templates…</p>
            ) : templates.length === 0 ? (
              <p className="text-xs text-danger">No active templates for this channel yet.</p>
            ) : (
              <select
                value={templateId} onChange={(e) => setTemplateId(e.target.value)} required
                className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card"
              >
                <option value="">Select a template</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            )}
          </div>

          {neededVariables.length > 0 && (
            <div className="space-y-2">
              {neededVariables.map((name) => (
                <div key={name}>
                  <label className="block text-xs text-text/60 mb-1">{`{{${name}}}`}</label>
                  <input
                    value={extraVariables[name] ?? ""}
                    onChange={(e) => setExtraVariables((prev) => ({ ...prev, [name]: e.target.value }))}
                    className="w-full rounded-xl border border-border px-3.5 py-2 text-sm"
                  />
                </div>
              ))}
            </div>
          )}

          <div className="mt-2 flex justify-end gap-2.5">
            <button type="button" onClick={onClose} className="rounded-lg border border-border text-sm font-medium py-2 px-3.5 text-text hover:bg-background">
              Close
            </button>
            <button
              type="submit" disabled={!templateId || isSubmitting}
              className="hover-lift rounded-lg bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-4 shadow-card disabled:opacity-50"
            >
              {isSubmitting ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
