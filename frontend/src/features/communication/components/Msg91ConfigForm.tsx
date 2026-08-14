import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { getErrorMessage } from "@/features/customer/errors";
import {
  createIntegrationConfig,
  testDraftConnection,
  testIntegrationConnection,
  updateIntegrationConfig,
  type IntegrationConfig,
  type TestConnectionResult,
} from "@/features/integrations/api";
import { ConnectionCheckList } from "@/features/integrations/components/ConnectionCheckList";
import { fieldsFor, type ProviderField, type ProviderFieldSection } from "@/features/integrations/providerFields";
import { Icon } from "@/theme/icons";

const SECTION_TITLES: Record<ProviderFieldSection, string> = {
  credentials: "A. Credentials",
  channel: "B. Channel Configuration",
  webhook: "C. Delivery & Webhook Configuration",
};

function isRequired(field: ProviderField) {
  return !field.optional && !field.toggle;
}

function FieldInput({
  field, value, onChange, showValue, onToggleShow,
}: {
  field: ProviderField;
  value: string;
  onChange: (v: string) => void;
  showValue: boolean;
  onToggleShow: () => void;
}) {
  if (field.toggle) {
    return (
      <select value={value || "false"} onChange={(e) => onChange(e.target.value)} className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm">
        <option value="false">Disabled</option>
        <option value="true">Enabled</option>
      </select>
    );
  }
  if (!field.secret) {
    return (
      <input
        type="text" value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm"
      />
    );
  }
  return (
    <div className="relative mt-1">
      <input
        type={showValue ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)}
        className="block w-full rounded border border-border px-3 py-2 pr-9 text-sm [&::-ms-reveal]:hidden [&::-ms-clear]:hidden"
      />
      <button
        type="button" onClick={onToggleShow} tabIndex={-1}
        aria-label={showValue ? "Hide value" : "Show value"}
        className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-text/40 hover:text-text/70"
      >
        <Icon name={showValue ? "eye-off" : "eye"} className="h-4 w-4" />
      </button>
    </div>
  );
}

interface Msg91ConfigFormProps {
  channel: "sms" | "whatsapp" | "email";
  label: string;
  existingConfig: IntegrationConfig | null;
  onSaved: () => void;
  onCancel: () => void;
}

// Dedicated MSG91 configuration form (Stage 4 UI hardening) — replaces the generic,
// multi-provider CreateConfigForm reuse on this screen with a fixed-shape layout matching
// the Owner-facing spec exactly: A. Credentials / B. Channel Configuration / C. Delivery &
// Webhook Configuration / D. Test & Save. Still built entirely on Module 9A's existing
// encrypted IntegrationConfig storage/API (create/update/test) — no new credential store.
export function Msg91ConfigForm({ channel, label, existingConfig, onSaved, onCancel }: Msg91ConfigFormProps) {
  const fields = fieldsFor(channel, "msg91");
  const bySection = (section: ProviderFieldSection) => fields.filter((f) => (f.section ?? "channel") === section);

  const [name, setName] = useState(existingConfig?.name ?? `MSG91 ${label}`);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const f of fields) initial[f.key] = existingConfig?.config[f.key] ?? (f.toggle ? "false" : "");
    return initial;
  });
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [testedSnapshot, setTestedSnapshot] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const setField = (key: string, value: string) => {
    setFieldValues((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
    setTestedSnapshot(null);
    setTestError(null);
  };

  const requiredFields = fields.filter(isRequired);
  const missingRequired = requiredFields.filter((f) => !(fieldValues[f.key] || "").trim());
  const requiredFieldsFilled = Boolean(name.trim()) && missingRequired.length === 0;
  const currentSnapshot = JSON.stringify(fieldValues);
  // Create flow: prove credentials work before Save is allowed, same rule the generic
  // wizard already enforces for every non-Meta provider. Edit flow: Save stays available
  // without a fresh test (matching IntegrationDetailsPage's own edit form) — the backend
  // already clears last_success_at/is_active whenever a real credential change is saved,
  // forcing re-verification before the config can be Activated again.
  const isVerifiedForCreate = testResult?.success === true && testedSnapshot === currentSnapshot;
  const canSave = existingConfig ? requiredFieldsFilled : requiredFieldsFilled && isVerifiedForCreate;

  const handleDraftTest = async () => {
    setTestError(null);
    setIsTesting(true);
    try {
      const result = await testDraftConnection({ integration_type: channel, provider: "msg91", config: fieldValues });
      setTestResult(result);
      setTestedSnapshot(result.success ? currentSnapshot : null);
    } catch (err) {
      setTestError(getErrorMessage(err));
    } finally {
      setIsTesting(false);
    }
  };

  const handleSavedConfigTest = async () => {
    if (!existingConfig) return;
    setTestError(null);
    setIsTesting(true);
    try {
      const result = await testIntegrationConnection(existingConfig.id);
      setTestResult(result);
    } catch (err) {
      setTestError(getErrorMessage(err));
    } finally {
      setIsTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAttemptedSubmit(true);
    if (!canSave) return;
    setSaveError(null);
    setIsSaving(true);
    try {
      if (existingConfig) {
        // Fields left exactly as-loaded (secret fields still showing their masked
        // "****last4" value, non-secret fields untouched) are sent back unchanged — the
        // backend's update_config compares against mask_secret(current) and preserves the
        // real encrypted value; only a genuinely different value triggers re-encryption.
        const changed = Object.fromEntries(Object.entries(fieldValues).filter(([, v]) => v !== ""));
        const payload: { name?: string; config?: Record<string, string> } = { config: changed };
        if (name.trim() && name.trim() !== existingConfig.name) payload.name = name.trim();
        await updateIntegrationConfig(existingConfig.id, payload);
      } else {
        await createIntegrationConfig({ integration_type: channel, provider: "msg91", name: name.trim(), config: fieldValues });
      }
      onSaved();
    } catch (err) {
      setSaveError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const renderSection = (section: ProviderFieldSection) => {
    const sectionFields = bySection(section);
    if (sectionFields.length === 0) return null;
    return (
      <div key={section} className="mb-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text/50">{SECTION_TITLES[section]}</h4>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {sectionFields.map((field) => {
            const showError = attemptedSubmit && isRequired(field) && !(fieldValues[field.key] || "").trim();
            return (
              <label key={field.key} className="text-xs text-text/60">
                {field.label} {field.optional && <span className="text-text/35">(optional)</span>}
                <FieldInput
                  field={field} value={fieldValues[field.key] || ""} onChange={(v) => setField(field.key, v)}
                  showValue={Boolean(visible[field.key])} onToggleShow={() => setVisible((prev) => ({ ...prev, [field.key]: !prev[field.key] }))}
                />
                {field.helpText && <p className="mt-1 text-[11px] leading-snug text-text/45">{field.helpText}</p>}
                {showError && <p className="mt-1 text-[11px] text-danger">Required.</p>}
              </label>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <form onSubmit={handleSubmit}>
      <FormField label="Configuration Name" value={name} onChange={(e) => setName(e.target.value)} required />

      {renderSection("credentials")}
      {renderSection("channel")}
      {renderSection("webhook")}

      <div className="mb-2">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text/50">D. Test &amp; Save</h4>
        <div className="flex flex-wrap items-center gap-3">
          {existingConfig ? (
            <Button variant="secondary" size="sm" disabled={isTesting} onClick={handleSavedConfigTest}>
              {isTesting ? "Testing…" : "Test Connection"}
            </Button>
          ) : (
            <Button variant="secondary" size="sm" disabled={!requiredFieldsFilled || isTesting} onClick={handleDraftTest}>
              {isTesting ? "Testing…" : "Test Connection"}
            </Button>
          )}
          <Button type="submit" size="sm" disabled={!canSave || isSaving}>
            {isSaving ? "Saving…" : existingConfig ? "Save Changes" : "Save Configuration"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </div>

        {!existingConfig && !isVerifiedForCreate && requiredFieldsFilled && (
          <p className="mt-2 text-xs text-text/50">Test the connection successfully before saving.</p>
        )}
        {existingConfig && (
          <p className="mt-2 text-xs text-text/50">
            Test Connection checks the currently saved credentials. Save changes first, then test again to verify a credential change.
          </p>
        )}

        {testError && <p className="mt-2 text-sm text-danger">{testError}</p>}
        {testResult && (
          <div className={`mt-3 rounded border px-3 py-3 ${testResult.success ? "border-success/30 bg-success/5" : "border-danger/30 bg-danger/5"}`}>
            {testResult.checks ? (
              <ConnectionCheckList checks={testResult.checks} />
            ) : (
              <p className={`text-sm ${testResult.success ? "text-success" : "text-danger"}`}>
                {testResult.success ? "Connected successfully." : testResult.error_message || "Connection failed."}
              </p>
            )}
          </div>
        )}
        {saveError && <p className="mt-2 text-sm text-danger">{saveError}</p>}
      </div>
    </form>
  );
}
