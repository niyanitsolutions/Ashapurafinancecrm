import { useEffect, useState } from "react";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import { ConnectionCheckList } from "@/features/integrations/components/ConnectionCheckList";
import {
  activateIntegrationConfig,
  createIntegrationConfig,
  disableIntegrationConfig,
  enableIntegrationConfig,
  listIntegrationConfigs,
  listIntegrationProviders,
  testIntegrationConnection,
  type IntegrationConfig,
  type IntegrationProvider,
  type TestConnectionResult,
} from "@/features/integrations/api";
import { CreateConfigForm } from "@/features/integrations/pages/IntegrationListPage";

const CHANNELS = [
  { type: "sms", label: "SMS" },
  { type: "whatsapp", label: "WhatsApp" },
  { type: "email", label: "Email" },
] as const;

const WEBHOOK_PATH = "/communication/webhooks/msg91";

// Reuses Module 9A's own encrypted IntegrationConfig storage/API — no separate
// credential store for MSG91. See docs/COMMUNICATION.md (Stage 2 of the Geo Fencing/
// Temporary Permissions/MSG91 request).
export function CommunicationProvidersPage() {
  const [configs, setConfigs] = useState<IntegrationConfig[]>([]);
  const [providers, setProviders] = useState<IntegrationProvider[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [addingChannel, setAddingChannel] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestConnectionResult>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    listIntegrationConfigs()
      .then((all) => setConfigs(all.filter((c) => c.provider === "msg91")))
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);
  useEffect(() => {
    listIntegrationProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  const configFor = (type: string) => configs.find((c) => c.integration_type === type);

  const runAction = async (id: string, action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    setBusyId(id);
    try {
      await action();
      setMessage(successMessage);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleTest = async (config: IntegrationConfig) => {
    setError(null);
    setBusyId(config.id);
    try {
      const result = await testIntegrationConnection(config.id);
      setTestResults((prev) => ({ ...prev, [config.id]: result }));
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const webhookUrl = `${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}${WEBHOOK_PATH}?secret=<your webhook_secret>`;

  return (
    <SimplePageLayout title="Communication Providers">
      <p className="mb-4 text-sm text-text/60">
        MSG91 configuration for SMS, WhatsApp, and Email. Credentials are stored encrypted, backend-only — never returned in full, never logged.
        Reuses the same configuration storage as Connections (API Connections).
      </p>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <h2 className="text-sm font-semibold text-text mb-1">MSG91</h2>
        <p className="text-xs text-text/60 mb-4">One card per channel — each is configured, tested, and enabled independently.</p>

        <div className="divide-y divide-border">
          {CHANNELS.map(({ type, label }) => {
            const config = configFor(type);
            const testResult = config ? testResults[config.id] : undefined;
            return (
              <div key={type} className="py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-text">{label}</span>
                    <span className="ml-3 text-xs">
                      {!config ? (
                        <span className="text-text/40">Not configured</span>
                      ) : config.is_active ? (
                        <span className="text-success">Active</span>
                      ) : config.is_enabled ? (
                        <span className="text-text/60">Configured</span>
                      ) : (
                        <span className="text-text/40">Disabled</span>
                      )}
                    </span>
                  </div>
                  <div className="space-x-3 text-xs">
                    {!config && (
                      <button
                        type="button" onClick={() => setAddingChannel(addingChannel === type ? null : type)}
                        className="text-primary hover:underline"
                      >
                        {addingChannel === type ? "Cancel" : "+ Add"}
                      </button>
                    )}
                    {config && (
                      <>
                        <button type="button" disabled={busyId === config.id} onClick={() => handleTest(config)} className="text-primary hover:underline disabled:opacity-50">
                          Test
                        </button>
                        {config.is_enabled ? (
                          <button
                            type="button" disabled={busyId === config.id}
                            onClick={() => runAction(config.id, () => disableIntegrationConfig(config.id), `${label} disabled.`)}
                            className="text-text/60 hover:underline disabled:opacity-50"
                          >
                            Disable
                          </button>
                        ) : (
                          <button
                            type="button" disabled={busyId === config.id}
                            onClick={() => runAction(config.id, () => enableIntegrationConfig(config.id), `${label} enabled.`)}
                            className="text-text/60 hover:underline disabled:opacity-50"
                          >
                            Enable
                          </button>
                        )}
                        {!config.is_active && (
                          <button
                            type="button" disabled={busyId === config.id}
                            onClick={() => runAction(config.id, () => activateIntegrationConfig(config.id), `${label} activated.`)}
                            className="text-text/60 hover:underline disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {config && (
                  <p className="mt-1 text-xs text-text/50">
                    {config.name} · Last tested: {config.last_tested_at ? new Date(config.last_tested_at).toLocaleString() : "Never"}
                  </p>
                )}

                {testResult && (
                  <div className={`mt-2 rounded border px-3 py-2 text-xs ${testResult.success ? "border-success/30 bg-success/5" : "border-danger/30 bg-danger/5"}`}>
                    {testResult.checks ? (
                      <ConnectionCheckList checks={testResult.checks} />
                    ) : (
                      <p className={testResult.success ? "text-success" : "text-danger"}>
                        {testResult.success ? "✓ Connection successful" : `✕ Connection failed — ${testResult.error_message || "Unable to authenticate with MSG91."}`}
                      </p>
                    )}
                  </div>
                )}

                {addingChannel === type && !config && (
                  <div className="mt-3 rounded border border-border p-4">
                    <CreateConfigForm
                      providers={providers.filter((p) => p.integration_type === type && p.provider === "msg91")}
                      onSubmit={async (payload) => {
                        setError(null);
                        try {
                          await createIntegrationConfig(payload);
                          setAddingChannel(null);
                          setMessage(`${label} configured.`);
                          load();
                        } catch (err) {
                          setError(getErrorMessage(err));
                        }
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card p-6">
        <h2 className="text-sm font-semibold text-text mb-2">Delivery Webhook</h2>
        <p className="text-xs text-text/60 mb-2">
          To receive real delivery confirmations (not just provider acceptance) for SMS, set a Webhook Secret on the SMS or WhatsApp configuration
          above, then configure this URL as the SMS Delivery Report webhook in your MSG91 dashboard:
        </p>
        <code className="block rounded bg-background px-3 py-2 text-xs break-all">{webhookUrl}</code>
        <p className="mt-2 text-xs text-text/50">
          Only SMS delivery reports are confirmed against MSG91's own documentation in this environment — see the known limitations for WhatsApp
          delivery report field names.
        </p>
      </div>
    </SimplePageLayout>
  );
}
