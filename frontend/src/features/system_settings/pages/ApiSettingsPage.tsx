import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  activateApiSetting,
  type ApiSetting,
  createApiSetting,
  deactivateApiSetting,
  listApiSettings,
  updateApiSetting,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

// Config values (API keys/secrets) are write-only — the backend never echoes them back,
// only the configured key *names* (see docs/decisions/DECISIONS.md). The Owner supplies
// a single key/value pair per add here; updating merges into the existing encrypted blob.
export function ApiSettingsPage() {
  const [items, setItems] = useState<ApiSetting[]>([]);
  const [newProvider, setNewProvider] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newConfigKey, setNewConfigKey] = useState("");
  const [newConfigValue, setNewConfigValue] = useState("");
  const [addingKeyFor, setAddingKeyFor] = useState<string | null>(null);
  const [addKeyName, setAddKeyName] = useState("");
  const [addKeyValue, setAddKeyValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    listApiSettings()
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProvider.trim() || !newLabel.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const config = newConfigKey.trim() ? { [newConfigKey.trim()]: newConfigValue } : {};
      await createApiSetting({ provider: newProvider.trim(), label: newLabel.trim(), config });
      setNewProvider("");
      setNewLabel("");
      setNewConfigKey("");
      setNewConfigValue("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onAddKey = async (id: string) => {
    if (!addKeyName.trim()) return;
    setError(null);
    try {
      await updateApiSetting(id, { config: { [addKeyName.trim()]: addKeyValue } });
      setAddingKeyFor(null);
      setAddKeyName("");
      setAddKeyValue("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onToggleStatus = async (item: ApiSetting) => {
    setError(null);
    try {
      if (item.status === "active") await deactivateApiSetting(item.id);
      else await activateApiSetting(item.id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="API Settings">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="mb-6 grid grid-cols-2 gap-3 max-w-2xl">
        <FormField label="Provider" value={newProvider} onChange={(e) => setNewProvider(e.target.value)} placeholder="e.g. meta / whatsapp / sms / smtp / maps" />
        <FormField label="Label" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="e.g. Primary SMS Gateway" />
        <FormField label="Config key (optional)" value={newConfigKey} onChange={(e) => setNewConfigKey(e.target.value)} placeholder="e.g. api_key" />
        <FormField label="Config value" value={newConfigValue} onChange={(e) => setNewConfigValue(e.target.value)} type="password" />
        <div className="col-span-2">
          <SubmitButton isSubmitting={isSubmitting}>Add Provider Config</SubmitButton>
        </div>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">Label</th>
              <th className="px-4 py-3">Configured Keys</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text/50">
                  No API settings yet.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background align-top">
                <td className="px-4 py-3">{item.provider}</td>
                <td className="px-4 py-3">{item.label}</td>
                <td className="px-4 py-3">
                  {item.configured_keys.length > 0 ? item.configured_keys.join(", ") : "—"}
                  {addingKeyFor === item.id ? (
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        className="w-28 rounded border border-border px-2 py-1"
                        placeholder="key"
                        value={addKeyName}
                        onChange={(e) => setAddKeyName(e.target.value)}
                      />
                      <input
                        className="w-28 rounded border border-border px-2 py-1"
                        placeholder="value"
                        type="password"
                        value={addKeyValue}
                        onChange={(e) => setAddKeyValue(e.target.value)}
                      />
                      <button type="button" className="text-primary hover:underline" onClick={() => onAddKey(item.id)}>
                        Save
                      </button>
                      <button type="button" className="text-text/60 hover:underline" onClick={() => setAddingKeyFor(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button type="button" className="mt-1 block text-primary hover:underline" onClick={() => setAddingKeyFor(item.id)}>
                      + Add/update key
                    </button>
                  )}
                </td>
                <td className="px-4 py-3 capitalize">{item.status}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(item)}>
                    {item.status === "active" ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
