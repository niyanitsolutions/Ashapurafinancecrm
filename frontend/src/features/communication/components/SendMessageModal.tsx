import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { Modal } from "@/components/overlays/Modal";
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

const SEND_MESSAGE_FORM_ID = "send-message-form";

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
    <Modal
      open
      onClose={onClose}
      title="Send Message"
      description={entityLabel}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button type="submit" form={SEND_MESSAGE_FORM_ID} size="sm" disabled={!templateId} loading={isSubmitting}>
            Send
          </Button>
        </>
      }
    >
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {result && (
        <p className={`mb-3 text-sm ${result.success ? "text-success" : "text-danger"}`}>
          {result.success ? "✓ Message sent." : `✕ ${result.error || "Message could not be sent."}`}
        </p>
      )}

      <form id={SEND_MESSAGE_FORM_ID} onSubmit={onSubmit}>
        <div className="mb-4">
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

        {isLoadingTemplates ? (
          <p className="text-xs text-text/50 mb-4">Loading templates…</p>
        ) : templates.length === 0 ? (
          <p className="text-xs text-danger mb-4">No active templates for this channel yet.</p>
        ) : (
          <SelectField
            label="Template"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            required
            placeholder="Select a template"
            options={templates.map((t) => ({ value: t.id, label: t.name }))}
          />
        )}

        {neededVariables.length > 0 &&
          neededVariables.map((name) => (
            <FormField
              key={name}
              label={`{{${name}}}`}
              value={extraVariables[name] ?? ""}
              onChange={(e) => setExtraVariables((prev) => ({ ...prev, [name]: e.target.value }))}
            />
          ))}
      </form>
    </Modal>
  );
}
