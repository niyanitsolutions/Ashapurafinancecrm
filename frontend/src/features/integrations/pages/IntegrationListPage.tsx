import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import { ConnectionCheckList } from "@/features/integrations/components/ConnectionCheckList";
import {
  createIntegrationConfig,
  listIntegrationConfigs,
  listIntegrationProviders,
  testDraftConnection,
  testIntegrationConnection,
  type IntegrationConfig,
  type IntegrationProvider,
  type TestConnectionResult,
} from "@/features/integrations/api";
import { fieldsFor } from "@/features/integrations/providerFields";

// Exported (additive — no behavior change to this page) so the Communication Providers
// page (Settings, Stage 2 of the Geo Fencing/MSG91 request) can reuse the exact same
// credential-entry + Test Connection flow for MSG91 instead of duplicating it.
export const TYPE_LABELS: Record<string, string> = { meta: "Meta", whatsapp: "WhatsApp", sms: "SMS", email: "Email", maps: "Google Maps" };

interface RevealedWebhook {
  configId: string;
  callbackPath: string;
  verifyToken: string;
  secret: string;
}

export function IntegrationListPage() {
  const [configs, setConfigs] = useState<IntegrationConfig[]>([]);
  const [providers, setProviders] = useState<IntegrationProvider[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [revealedWebhook, setRevealedWebhook] = useState<RevealedWebhook | null>(null);

  const load = () => {
    setIsLoading(true);
    listIntegrationConfigs()
      .then(setConfigs)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);
  useEffect(() => {
    listIntegrationProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  const byType = configs.reduce<Record<string, IntegrationConfig[]>>((acc, c) => {
    (acc[c.integration_type] ??= []).push(c);
    return acc;
  }, {});

  return (
    <SimplePageLayout title="API Connections">
      <p className="mb-4 text-sm text-text/60">
        Configuration and connection management only — no messages are sent, no leads are fetched from here. Each integration type can have multiple
        named configurations (e.g. "Meta Production", "Meta Sandbox"); exactly one can be Active at a time.
      </p>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      {revealedWebhook && (
        <div className="mb-6 rounded border border-warning/30 bg-warning/10 p-4 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-semibold text-warning">Copy these into Meta's Webhook setup now — you won't see them again</span>
            <button type="button" onClick={() => setRevealedWebhook(null)} className="text-xs text-text/50 hover:underline">Dismiss</button>
          </div>
          <dl className="space-y-1.5">
            <div><dt className="inline text-text/60">Callback URL: </dt><dd className="inline font-mono">{`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}${revealedWebhook.callbackPath}`}</dd></div>
            <div><dt className="inline text-text/60">Verify Token: </dt><dd className="inline font-mono">{revealedWebhook.verifyToken}</dd></div>
            <div><dt className="inline text-text/60">Webhook Secret: </dt><dd className="inline font-mono">{revealedWebhook.secret}</dd></div>
          </dl>
          <Link to={`/integrations/${revealedWebhook.configId}`} className="mt-3 inline-block text-primary hover:underline">Continue to Connect Facebook →</Link>
        </div>
      )}

      <div className="mb-6">
        <Button size="sm" onClick={() => setShowForm(true)}>
          + Add Configuration
        </Button>
      </div>

      {showForm && (
        <Modal open onClose={() => setShowForm(false)} title="New Configuration" size="lg">
          <CreateConfigForm
            providers={providers}
            onSubmit={async (payload) => {
              setError(null);
              setMessage(null);
              setRevealedWebhook(null);
              try {
                const created = await createIntegrationConfig(payload);
                if (created.webhook_callback_path) {
                  // Meta: no access_token is entered manually anymore, so a Test
                  // Connection here would just fail on a missing token — Connect
                  // Facebook (on the details page) is what proves this config works.
                  setRevealedWebhook({
                    configId: created.id, callbackPath: created.webhook_callback_path,
                    verifyToken: created.config.webhook_verify_token, secret: created.config.webhook_secret,
                  });
                } else {
                  // Re-runs the real (persisted) test once against the new config so its
                  // last_success_at/IntegrationTestLog history is populated exactly like any
                  // other test — the draft test itself is intentionally never persisted.
                  await testIntegrationConnection(created.id);
                  setMessage("Configuration created and verified.");
                }
                setShowForm(false);
                load();
              } catch (err) {
                setError(getErrorMessage(err));
              }
            }}
          />
        </Modal>
      )}

      {isLoading && <p className="text-sm text-text/50">Loading…</p>}
      {!isLoading && configs.length === 0 && (
        <EmptyState icon="integrations" title="No integrations configured yet" description="Add your first configuration to start connecting a provider." primaryAction={{ label: "+ Add Configuration", onClick: () => setShowForm(true) }} />
      )}
      <div className="space-y-6">
        {Object.entries(byType).map(([type, items]) => (
          <div key={type}>
            <h3 className="text-sm font-semibold text-text/70 mb-2">{TYPE_LABELS[type] || type}</h3>
            <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-text/60">
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Provider</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Last Tested</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((config) => (
                    <tr key={config.id} className="border-b border-border last:border-0 hover:bg-background">
                      <td className="px-4 py-3">
                        <Link to={`/integrations/${config.id}`} className="text-primary hover:underline">{config.name}</Link>
                      </td>
                      <td className="px-4 py-3">{config.provider}</td>
                      <td className="px-4 py-3">
                        {config.is_active ? (
                          <span className="text-success">Active</span>
                        ) : config.is_enabled ? (
                          <span className="text-text/60">Enabled</span>
                        ) : (
                          <span className="text-text/40">Disabled</span>
                        )}
                      </td>
                      <td className="px-4 py-3">{config.last_tested_at ? new Date(config.last_tested_at).toLocaleString() : "Never"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}

export function StepHeading({ step, title }: { step: number; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{step}</span>
      <span className="text-xs font-semibold uppercase tracking-wide text-text/50">{title}</span>
    </div>
  );
}

export function CreateConfigForm({
  providers, onSubmit,
}: {
  providers: IntegrationProvider[];
  onSubmit: (payload: { integration_type: string; provider: string; name: string; config: Record<string, string> }) => void;
}) {
  const [integrationType, setIntegrationType] = useState("");
  const [provider, setProvider] = useState("");
  const [name, setName] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [testedSnapshot, setTestedSnapshot] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const availableProviders = providers.filter((p) => p.integration_type === integrationType);
  const fields = integrationType ? fieldsFor(integrationType, provider) : [];
  // Meta has no Access Token to test yet at this point — that's what Connect Facebook
  // (OAuth, from the details page after Save) acquires. Test Connection only applies
  // once a real token exists, so Meta skips straight from credentials to Save.
  const isMeta = integrationType === "meta";

  // Any change to type/provider/credentials invalidates a previous successful test —
  // Save stays locked until the *current* values have been proven, mirroring the backend's
  // own rule (editing a saved config's credentials clears its last_success_at the same way).
  const currentSnapshot = JSON.stringify({ integrationType, config: fieldValues });
  const requiredFieldsFilled = Boolean(integrationType && provider && name) && fields.every((f) => f.toggle || (fieldValues[f.key] || "").trim() !== "");
  const isVerified = isMeta ? requiredFieldsFilled : testResult?.success === true && testedSnapshot === currentSnapshot;

  const resetTestState = () => {
    setTestResult(null);
    setTestedSnapshot(null);
    setTestError(null);
  };

  const handleTest = async () => {
    setTestError(null);
    setIsTesting(true);
    try {
      const result = await testDraftConnection({ integration_type: integrationType, config: fieldValues });
      setTestResult(result);
      setTestedSnapshot(result.success ? currentSnapshot : null);
    } catch (err) {
      setTestError(getErrorMessage(err));
    } finally {
      setIsTesting(false);
    }
  };

  const missingPermissions = testResult?.checks?.find((c) => c.key === "permissions" && !c.passed);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ integration_type: integrationType, provider, name, config: fieldValues });
      }}
    >
      <ol className="space-y-5">
        <li>
          <StepHeading step={1} title="Choose Provider" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <select
              value={integrationType}
              onChange={(e) => { setIntegrationType(e.target.value); setProvider(""); setFieldValues({}); resetTestState(); }}
              className="rounded border border-border px-3 py-2 text-sm" required
            >
              <option value="" disabled>Integration Type…</option>
              {Array.from(new Set(providers.map((p) => p.integration_type))).map((type) => (
                <option key={type} value={type}>{TYPE_LABELS[type] || type}</option>
              ))}
            </select>
            <select
              value={provider}
              onChange={(e) => { setProvider(e.target.value); resetTestState(); }}
              className="rounded border border-border px-3 py-2 text-sm" required disabled={!integrationType}
            >
              <option value="" disabled>Provider…</option>
              {availableProviders.map((p) => (
                <option key={p.id} value={p.provider}>{p.label}</option>
              ))}
            </select>
            <input
              placeholder="Name (e.g. Meta Production)" value={name} onChange={(e) => setName(e.target.value)}
              className="rounded border border-border px-3 py-2 text-sm" required
            />
          </div>
        </li>

        {fields.length > 0 && (
          <li>
            <StepHeading step={2} title="Enter Credentials" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {fields.map((field) => (
                <label key={field.key} className="text-xs text-text/60">
                  {field.label}
                  {field.toggle ? (
                    <select
                      value={fieldValues[field.key] || "false"}
                      onChange={(e) => { setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value })); resetTestState(); }}
                      className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm"
                    >
                      <option value="false">Disabled</option>
                      <option value="true">Enabled</option>
                    </select>
                  ) : (
                    <input
                      type={field.secret ? "password" : "text"} value={fieldValues[field.key] || ""}
                      onChange={(e) => { setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value })); resetTestState(); }}
                      className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm"
                    />
                  )}
                </label>
              ))}
            </div>
          </li>
        )}

        {isMeta ? (
          <li>
            <StepHeading step={3} title="Connect Facebook (after saving)" />
            <p className="text-sm text-text/60">
              Save below, then use the "Connect Facebook" button on the configuration's detail page to log in, pick a Page/Ad Account/Lead Forms,
              and finish setup — no Access Token to paste here.
            </p>
          </li>
        ) : (
          <li>
            <StepHeading step={3} title="Test Connection" />
            <Button variant="secondary" size="sm" className="mb-3" disabled={!requiredFieldsFilled || isTesting} onClick={handleTest}>
              {isTesting ? "Testing…" : "Test Connection"}
            </Button>
            {testError && <p className="mb-2 text-sm text-danger">{testError}</p>}
            {testResult && (
              <div className={`rounded border px-3 py-3 ${testResult.success ? "border-success/30 bg-success/5" : "border-danger/30 bg-danger/5"}`}>
                {testResult.checks ? (
                  <ConnectionCheckList checks={testResult.checks} />
                ) : (
                  <p className={`text-sm ${testResult.success ? "text-success" : "text-danger"}`}>
                    {testResult.success ? "Connected successfully." : testResult.error_message || "Connection failed."}
                  </p>
                )}
                {missingPermissions && (
                  <div className="mt-3 rounded border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                    Missing Permissions — grant them in Meta Business Manager, then reconnect and test again.
                  </div>
                )}
              </div>
            )}
          </li>
        )}

        <li>
          <StepHeading step={4} title="Save" />
          <SubmitButton disabled={!isVerified}>Save Configuration</SubmitButton>
          {!isVerified && <p className="mt-1.5 text-xs text-text/50">{isMeta ? "Fill in App ID and App Secret first." : "Test the connection successfully first."}</p>}
        </li>
      </ol>
    </form>
  );
}
