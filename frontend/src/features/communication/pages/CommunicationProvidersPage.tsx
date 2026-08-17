import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { Msg91ConfigForm } from "@/features/communication/components/Msg91ConfigForm";
import { getErrorMessage } from "@/features/customer/errors";
import { ConnectionCheckList } from "@/features/integrations/components/ConnectionCheckList";
import { formatISTDateTime } from "@/shared/dateFormat";
import {
  activateIntegrationConfig,
  disableIntegrationConfig,
  enableIntegrationConfig,
  listIntegrationConfigs,
  testIntegrationConnection,
  type IntegrationConfig,
  type TestConnectionResult,
} from "@/features/integrations/api";

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
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [openFormChannel, setOpenFormChannel] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestConnectionResult>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [disableTarget, setDisableTarget] = useState<{ config: IntegrationConfig; label: string } | null>(null);

  const load = () => {
    listIntegrationConfigs()
      .then((all) => setConfigs(all.filter((c) => c.provider === "msg91")))
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

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
    <SimplePageLayout
      title="Communication Providers"
      subtitle="MSG91 configuration for SMS, WhatsApp, and Email. Credentials are stored encrypted, backend-only — never returned in full, never logged."
    >
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
                <div className="flex flex-wrap items-center justify-between gap-3">
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
                  <div className="flex flex-wrap items-center gap-2">
                    {!config && (
                      <Button variant="secondary" size="sm" onClick={() => setOpenFormChannel(type)}>
                        + Add
                      </Button>
                    )}
                    {config && (
                      <>
                        <Button variant="secondary" size="sm" onClick={() => setOpenFormChannel(type)}>
                          Edit
                        </Button>
                        <Button variant="secondary" size="sm" disabled={busyId === config.id} onClick={() => handleTest(config)}>
                          Test
                        </Button>
                        {config.is_enabled ? (
                          <Button
                            variant="ghost" size="sm" disabled={busyId === config.id}
                            onClick={() => setDisableTarget({ config, label })}
                          >
                            Disable
                          </Button>
                        ) : (
                          <Button
                            variant="ghost" size="sm" disabled={busyId === config.id}
                            onClick={() => runAction(config.id, () => enableIntegrationConfig(config.id), `${label} enabled.`)}
                          >
                            Enable
                          </Button>
                        )}
                        {!config.is_active && (
                          <Button
                            variant="ghost" size="sm" disabled={busyId === config.id}
                            onClick={() => runAction(config.id, () => activateIntegrationConfig(config.id), `${label} activated.`)}
                          >
                            Activate
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {config && (
                  <p className="mt-1 text-xs text-text/50">
                    {config.name} · Last tested: {config.last_tested_at ? formatISTDateTime(config.last_tested_at) : "Never"}
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

                {openFormChannel === type && (
                  <Modal open onClose={() => setOpenFormChannel(null)} title={config ? `Edit ${label} Configuration` : `Add ${label} Configuration`} size="lg">
                    <Msg91ConfigForm
                      channel={type} label={label} existingConfig={config ?? null}
                      onSaved={() => {
                        setOpenFormChannel(null);
                        setMessage(config ? `${label} configuration updated.` : `${label} configured.`);
                        load();
                      }}
                      onCancel={() => setOpenFormChannel(null)}
                    />
                  </Modal>
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

      <ConfirmDialog
        open={disableTarget !== null}
        title="Disable Provider"
        message={disableTarget ? `Disable ${disableTarget.label}? No further messages will be sent through this channel until it's re-enabled.` : ""}
        confirmLabel="Disable"
        confirmVariant="danger"
        onConfirm={async () => {
          if (!disableTarget) return;
          await runAction(disableTarget.config.id, () => disableIntegrationConfig(disableTarget.config.id), `${disableTarget.label} disabled.`);
          setDisableTarget(null);
        }}
        onClose={() => setDisableTarget(null)}
      />
    </SimplePageLayout>
  );
}
