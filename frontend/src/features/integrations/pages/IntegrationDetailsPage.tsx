import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Pagination } from "@/components/tables/Pagination";
import { getErrorMessage } from "@/features/customer/errors";
import { ConnectionCheckList } from "@/features/integrations/components/ConnectionCheckList";
import {
  activateIntegrationConfig,
  connectMetaOAuth,
  disableIntegrationConfig,
  disconnectMeta,
  enableIntegrationConfig,
  getIntegrationConfig,
  getMetaStatus,
  getOAuthSession,
  listIntegrationTestLogs,
  listOAuthForms,
  startMetaOAuth,
  syncMetaForms,
  testIntegrationConnection,
  updateIntegrationConfig,
  type IntegrationConfig,
  type IntegrationTestLog,
  type MetaStatus,
  type OAuthOption,
  type OAuthSession,
  type TestConnectionResult,
} from "@/features/integrations/api";
import { fieldsFor } from "@/features/integrations/providerFields";
import { formatISTDateTime } from "@/shared/dateFormat";

const HEALTH_BADGE: Record<string, { label: string; icon: string; className: string }> = {
  healthy: { label: "Healthy", icon: "🟢", className: "text-success" },
  warning: { label: "Warning", icon: "🟡", className: "text-warning" },
  error: { label: "Error", icon: "🔴", className: "text-danger" },
};

const SETUP_STEPS: { key: keyof MetaStatus["setup_progress"]; label: string }[] = [
  { key: "credentials_entered", label: "Credentials" },
  { key: "test_connection_passed", label: "Test Connection" },
  { key: "saved", label: "Saved" },
  { key: "activated", label: "Activated" },
  { key: "webhook_verified", label: "Webhook Verified" },
  { key: "first_lead_received", label: "First Lead Received" },
];

function formatDate(value: string | null): string {
  return value ? formatISTDateTime(value) : "—";
}

function MetaConnectPanel({
  config, sessionId, onChanged, onError,
}: {
  config: IntegrationConfig;
  sessionId: string | null;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [session, setSession] = useState<OAuthSession | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [selectedAdAccountId, setSelectedAdAccountId] = useState("");
  const [forms, setForms] = useState<OAuthOption[]>([]);
  const [selectedFormIds, setSelectedFormIds] = useState<string[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      return;
    }
    getOAuthSession(config.id, sessionId)
      .then(setSession)
      .catch((err) => onError(getErrorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id, sessionId]);

  useEffect(() => {
    if (!sessionId || !selectedPageId) {
      setForms([]);
      setSelectedFormIds([]);
      return;
    }
    listOAuthForms(config.id, sessionId, selectedPageId)
      .then(setForms)
      .catch((err) => onError(getErrorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id, sessionId, selectedPageId]);

  const isConnected = Boolean(config.config.page_id);

  const handleConnectClick = async () => {
    setIsBusy(true);
    try {
      const { authorize_url } = await startMetaOAuth(config.id);
      window.location.href = authorize_url;
    } catch (err) {
      onError(getErrorMessage(err));
      setIsBusy(false);
    }
  };

  const handleFinishConnect = async () => {
    if (!sessionId || !selectedPageId) return;
    setIsBusy(true);
    try {
      await connectMetaOAuth(config.id, sessionId, { page_id: selectedPageId, ad_account_id: selectedAdAccountId || null, selected_forms: selectedFormIds });
      onChanged();
    } catch (err) {
      onError(getErrorMessage(err));
    } finally {
      setIsBusy(false);
    }
  };

  const handleDisconnect = async () => {
    setIsBusy(true);
    try {
      await disconnectMeta(config.id);
      onChanged();
    } catch (err) {
      onError(getErrorMessage(err));
    } finally {
      setIsBusy(false);
      setConfirmDisconnect(false);
    }
  };

  if (sessionId && session) {
    return (
      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Finish Connecting Facebook</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <label className="text-xs text-text/60">
            Facebook Page
            <select value={selectedPageId} onChange={(e) => setSelectedPageId(e.target.value)} className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm">
              <option value="">Select a Page…</option>
              {session.pages.map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.instagram_username ? ` (Instagram: @${p.instagram_username})` : ""}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-text/60">
            Ad Account (optional)
            <select value={selectedAdAccountId} onChange={(e) => setSelectedAdAccountId(e.target.value)} className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm">
              <option value="">None</option>
              {session.ad_accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
        </div>
        {selectedPageId && (
          <div className="mb-4">
            <span className="text-xs text-text/60">Lead Forms (leave all unchecked to accept leads from every form on this Page)</span>
            <div className="mt-1 space-y-1">
              {forms.length === 0 && <p className="text-xs text-text/40">No Lead Forms found on this Page yet.</p>}
              {forms.map((f) => (
                <label key={f.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox" checked={selectedFormIds.includes(f.id)}
                    onChange={(e) => setSelectedFormIds((prev) => (e.target.checked ? [...prev, f.id] : prev.filter((id) => id !== f.id)))}
                  />
                  {f.name}
                </label>
              ))}
            </div>
          </div>
        )}
        <Button disabled={!selectedPageId || isBusy} onClick={handleFinishConnect}>
          {isBusy ? "Connecting…" : "Connect"}
        </Button>
      </div>
    );
  }

  return (
    <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
      <h3 className="text-sm font-semibold text-text/70 mb-3">Meta Integration</h3>
      {isConnected ? (
        <>
          <div className="mb-4 flex items-center gap-2 text-sm font-medium text-success">🟢 Connected</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
            <div><span className="text-text/50">Facebook Page</span><div>{config.config.page_name || "—"}</div></div>
            <div><span className="text-text/50">Ad Account</span><div>{config.config.ad_account_id || "—"}</div></div>
            <div><span className="text-text/50">Lead Forms</span><div>{config.config.selected_forms ? config.config.selected_forms.split(",").length : "All"}</div></div>
            <div><span className="text-text/50">Last Sync</span><div>{formatDate(config.last_success_at)}</div></div>
          </div>
          <Button variant="danger" size="sm" disabled={isBusy} onClick={() => setConfirmDisconnect(true)}>
            Disconnect
          </Button>
          <ConfirmDialog
            open={confirmDisconnect}
            title="Disconnect Facebook"
            message="Disconnect this Page? Lead capture from Facebook will stop until you reconnect."
            confirmLabel="Disconnect"
            confirmVariant="danger"
            onConfirm={handleDisconnect}
            onClose={() => setConfirmDisconnect(false)}
          />
        </>
      ) : (
        <>
          <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text/40">⚪ Not Connected</div>
          <Button disabled={!config.config.app_id || !config.config.app_secret || isBusy} onClick={handleConnectClick}>
            {isBusy ? "Redirecting…" : "Connect Facebook"}
          </Button>
          {(!config.config.app_id || !config.config.app_secret) && <p className="mt-1.5 text-xs text-text/50">Set App ID and App Secret below first.</p>}
        </>
      )}
    </div>
  );
}

const SYNC_STATUS_LABEL: Record<string, { label: string; className: string }> = {
  healthy: { label: "Synced", className: "text-success" },
  warning: { label: "Attention Needed", className: "text-warning" },
  error: { label: "Error", className: "text-danger" },
};

// The at-a-glance panel an Owner/admin checks first when a lead "should have" arrived —
// consolidates what ConnectionHealthPanel/SetupProgressPanel already track plus the two
// genuinely new pieces of data (Last Token Refresh, Token Expiry Date) into one place
// with the two actions (Send Test Lead, Sync Forms) attached, so diagnosing a stalled
// integration doesn't require reading server logs.
function MetaStatusPanel({ config, status, onError }: { config: IntegrationConfig; status: MetaStatus | null; onError: (message: string) => void }) {
  const [isSyncingForms, setIsSyncingForms] = useState(false);
  const [syncedForms, setSyncedForms] = useState<OAuthOption[] | null>(null);
  const [showTestLeadHelp, setShowTestLeadHelp] = useState(false);

  const isConnected = Boolean(config.config.page_id);
  const connectionBadge = !isConnected
    ? { icon: "⚪", label: "Not Connected", className: "text-text/40" }
    : status?.health_status
      ? { icon: status.health_status === "healthy" ? "🟢" : status.health_status === "warning" ? "🟡" : "🔴", label: "Connected", className: HEALTH_BADGE[status.health_status].className }
      : { icon: "🟡", label: "Connected (not yet verified)", className: "text-warning" };

  const selectedFormIds = (config.config.selected_forms || "").split(",").filter(Boolean);

  const handleSyncForms = async () => {
    setIsSyncingForms(true);
    try {
      setSyncedForms(await syncMetaForms(config.id));
    } catch (err) {
      onError(getErrorMessage(err));
    } finally {
      setIsSyncingForms(false);
    }
  };

  return (
    <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text/70">Meta Integration Status</h3>
        <span className={`text-sm font-medium ${connectionBadge.className}`}>{connectionBadge.icon} {connectionBadge.label}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
        <div><span className="text-text/50">Facebook Page</span><div>{status?.connected_page_name || "—"}</div></div>
        <div><span className="text-text/50">Ad Account</span><div>{status?.connected_ad_account_id || "—"}</div></div>
        <div><span className="text-text/50">Lead Forms</span><div>{isConnected ? (status?.connected_form_count ?? "All") : "—"}</div></div>
        <div>
          <span className="text-text/50">Sync Status</span>
          <div className={status?.health_status ? SYNC_STATUS_LABEL[status.health_status].className : "text-text/40"}>
            {isConnected ? (status?.health_status ? SYNC_STATUS_LABEL[status.health_status].label : "Pending first check") : "Not connected"}
          </div>
        </div>
        <div><span className="text-text/50">Last Lead Received</span><div>{formatDate(status?.last_lead_received_at ?? null)}</div></div>
        <div><span className="text-text/50">Last Successful Webhook</span><div>{formatDate(status?.webhook_verified_at ?? null)}</div></div>
        <div><span className="text-text/50">Last Token Refresh</span><div>{formatDate(status?.last_token_refresh_at ?? null)}</div></div>
        <div><span className="text-text/50">Token Expiry Date</span><div>{formatDate(status?.user_token_expires_at ?? null)}</div></div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={() => setShowTestLeadHelp((v) => !v)}>
          Send Test Lead
        </Button>
        <Button variant="secondary" size="sm" disabled={!isConnected || isSyncingForms} onClick={handleSyncForms}>
          {isSyncingForms ? "Syncing…" : "Sync Forms"}
        </Button>
      </div>

      {showTestLeadHelp && (
        <div className="mt-3 rounded border border-border bg-background px-3 py-3 text-xs text-text/70">
          Open Meta&apos;s{" "}
          <a href="https://developers.facebook.com/tools/lead-ads-testing/" target="_blank" rel="noreferrer" className="text-primary hover:underline">
            Lead Ads Testing Tool
          </a>
          , select Page &quot;{status?.connected_page_name || "—"}&quot;, pick a Lead Form, and submit a test lead — it should appear on the Leads
          page within about 15 seconds without a manual refresh.
        </div>
      )}

      {syncedForms && (
        <div className="mt-3 text-xs text-text/60">
          <div className="mb-1 font-semibold">Forms on this Page ({syncedForms.length}):</div>
          <ul className="list-inside list-disc">
            {syncedForms.map((f) => (
              <li key={f.id}>
                {f.name}
                {selectedFormIds.length > 0 && !selectedFormIds.includes(f.id) && <span className="text-text/40"> — not selected</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConnectionHealthPanel({ status }: { status: MetaStatus }) {
  const badge = status.health_status ? HEALTH_BADGE[status.health_status] : null;
  return (
    <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
      <h3 className="text-sm font-semibold text-text/70 mb-3">Connection Health</h3>
      <div className="mb-4 flex items-center gap-2 text-sm font-medium">
        {badge ? (
          <span className={badge.className}>{badge.icon} {badge.label}</span>
        ) : (
          <span className="text-text/40">Not yet tested</span>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div><span className="text-text/50">Ad Accounts</span><div>{status.ad_accounts_count ?? "—"}</div></div>
        <div><span className="text-text/50">Pages</span><div>{status.pages_count ?? "—"}</div></div>
        <div><span className="text-text/50">Lead Forms</span><div>{status.lead_forms_count ?? "—"}</div></div>
        <div><span className="text-text/50">Sync Mode</span><div>Real-time (Webhook)</div></div>
        <div><span className="text-text/50">Webhook</span><div>{status.webhook_verified_at ? `Verified · ${formatDate(status.webhook_verified_at)}` : "Not yet verified"}</div></div>
        <div><span className="text-text/50">Last Lead Received</span><div>{formatDate(status.last_lead_received_at)}</div></div>
        <div><span className="text-text/50">Total Leads Imported</span><div>{status.total_leads_imported}</div></div>
        <div><span className="text-text/50">Connected Since</span><div>{formatDate(status.connected_since)}</div></div>
      </div>
      {status.missing_permissions.length > 0 && (
        <div className="mt-4 rounded border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          <div className="font-semibold mb-1">Missing Permissions</div>
          <ul className="space-y-0.5">
            {status.missing_permissions.map((p) => (
              <li key={p.permission}>❌ {p.permission} — {p.why_needed}</li>
            ))}
          </ul>
          <div className="mt-1">Go to Meta Business Manager → grant the permission → Reconnect.</div>
        </div>
      )}
    </div>
  );
}

function SetupProgressPanel({ status }: { status: MetaStatus }) {
  return (
    <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text/70">Setup Progress</h3>
        <span className="text-xs text-text/50">{status.completed_steps} / {status.total_steps} Completed</span>
      </div>
      <ul className="space-y-1.5">
        {SETUP_STEPS.map((step) => {
          const done = status.setup_progress[step.key];
          return (
            <li key={step.key} className="flex items-center gap-2 text-sm">
              <span className={done ? "text-success" : "text-text/30"}>{done ? "✓" : "○"}</span>
              <span className={done ? "text-text" : "text-text/50"}>{step.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function IntegrationDetailsPage() {
  const { configId } = useParams<{ configId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [config, setConfig] = useState<IntegrationConfig | null>(null);
  const [logs, setLogs] = useState<IntegrationTestLog[]>([]);
  const [metaStatus, setMetaStatus] = useState<MetaStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [configJustChanged, setConfigJustChanged] = useState(false);

  const oauthSessionId = searchParams.get("oauth_session");
  const oauthError = searchParams.get("oauth_error");
  const [confirmDisable, setConfirmDisable] = useState(false);
  const [logsPage, setLogsPage] = useState(1);
  const [logsPageSize, setLogsPageSize] = useState(10);

  const load = () => {
    if (!configId) return;
    setIsLoading(true);
    getIntegrationConfig(configId)
      .then((c) => {
        setConfig(c);
        setFieldValues({});
        if (c.integration_type === "meta") {
          getMetaStatus(configId).then(setMetaStatus).catch(() => setMetaStatus(null));
        }
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
    listIntegrationTestLogs(configId).then(setLogs).catch(() => setLogs([]));
  };

  useEffect(load, [configId]);

  if (!configId) return null;

  const clearOAuthParams = () => setSearchParams((prev) => { const next = new URLSearchParams(prev); next.delete("oauth_session"); next.delete("oauth_error"); return next; });

  const run = async (action: () => Promise<unknown>, successMessage: string, after?: () => void) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      load();
      after?.();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleTest = async () => {
    setError(null);
    setMessage(null);
    setIsTesting(true);
    try {
      const result = await testIntegrationConnection(configId);
      setTestResult(result);
      setConfigJustChanged(false);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsTesting(false);
    }
  };

  if (isLoading) return <SimplePageLayout title="Integration"><p className="text-sm text-text/50">Loading…</p></SimplePageLayout>;
  if (!config) return <SimplePageLayout title="Integration"><p className="text-sm text-danger">{error || "Not found."}</p></SimplePageLayout>;

  const fields = fieldsFor(config.integration_type, config.provider);
  const needsRetest = config.last_success_at === null;

  return (
    <SimplePageLayout title={config.name}>
      <div className="mb-4">
        <Link to="/integrations" className="text-sm text-primary hover:underline">← Back to Integrations</Link>
      </div>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      {oauthError && <p className="mb-4 text-sm text-danger">Facebook connection failed: {oauthError}</p>}

      {config.integration_type === "meta" && (
        <MetaConnectPanel
          config={config}
          sessionId={oauthSessionId}
          onChanged={() => {
            clearOAuthParams();
            setMessage("Facebook connected.");
            load();
          }}
          onError={(msg) => setError(msg)}
        />
      )}

      {config.integration_type === "meta" && <MetaStatusPanel config={config} status={metaStatus} onError={(msg) => setError(msg)} />}
      {metaStatus && <ConnectionHealthPanel status={metaStatus} />}
      {metaStatus && <SetupProgressPanel status={metaStatus} />}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
          <div><span className="text-text/50">Code</span><div>{config.integration_code}</div></div>
          <div><span className="text-text/50">Provider</span><div>{config.provider}</div></div>
          <div><span className="text-text/50">Last Success</span><div>{formatDate(config.last_success_at)}</div></div>
          <div><span className="text-text/50">Last Failure</span><div>{formatDate(config.last_failure_at)}</div></div>
        </div>
        {config.last_error_message && <p className="mb-4 text-sm text-danger">Last error: {config.last_error_message}</p>}
        {configJustChanged && (
          <div className="mb-4 rounded border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
            Configuration changed — test the connection again before activating.
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          {config.is_enabled ? (
            <Button variant="secondary" size="sm" onClick={() => setConfirmDisable(true)}>
              Disable
            </Button>
          ) : (
            <Button
              variant="secondary" size="sm" className="border-success text-success"
              onClick={() => run(() => enableIntegrationConfig(config.id), "Enabled.")}
            >
              Enable
            </Button>
          )}
          <ConfirmDialog
            open={confirmDisable}
            title="Disable Integration"
            message="Disable this integration? It will stop accepting or sending data until re-enabled."
            confirmLabel="Disable"
            confirmVariant="danger"
            onConfirm={() => run(() => disableIntegrationConfig(config.id), "Disabled.", () => setConfirmDisable(false))}
            onClose={() => setConfirmDisable(false)}
          />
          {!config.is_active && (
            <div>
              <Button size="sm" disabled={needsRetest} onClick={() => run(() => activateIntegrationConfig(config.id), "Set as the active configuration.")}>
                Set Active
              </Button>
              {needsRetest && <p className="mt-1 text-xs text-text/50">Test the connection successfully first.</p>}
            </div>
          )}
          <Button variant="secondary" size="sm" disabled={isTesting} onClick={handleTest}>
            {isTesting ? "Testing…" : "Test Connection"}
          </Button>
        </div>

        {testResult && (
          <div className={`mt-4 rounded border px-3 py-3 ${testResult.success ? "border-success/30 bg-success/5" : "border-danger/30 bg-danger/5"}`}>
            {testResult.checks ? (
              <>
                <ConnectionCheckList checks={testResult.checks} />
                {testResult.checks.some((c) => c.key === "token" && c.passed) && (
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 border-t border-border pt-3 text-xs text-text/60">
                    <div>Response Time: {testResult.response_time_ms}ms</div>
                    <div>Tested At: {formatISTDateTime(testResult.tested_at)}</div>
                  </div>
                )}
              </>
            ) : (
              <p className={`text-sm ${testResult.success ? "text-success" : "text-danger"}`}>
                {testResult.success ? "Connected successfully." : testResult.error_message || "Connection failed."}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Configuration</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const changed = Object.fromEntries(Object.entries(fieldValues).filter(([, v]) => v !== ""));
            if (Object.keys(changed).length === 0) return;
            setConfigJustChanged(true);
            setTestResult(null);
            run(() => updateIntegrationConfig(config.id, { config: changed }), "Configuration updated.");
          }}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            {fields.map((field) => (
              <label key={field.key} className="text-xs text-text/60">
                {field.label} {field.secret && <span className="text-text/40">(current: {config.config[field.key] || "not set"})</span>}
                <input
                  type={field.secret ? "password" : "text"} placeholder={field.secret ? "Leave blank to keep current value" : config.config[field.key] || ""}
                  value={fieldValues[field.key] || ""} onChange={(e) => setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm"
                />
              </label>
            ))}
          </div>
          <SubmitButton>Save Changes</SubmitButton>
        </form>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card">
        <div className="px-4 py-3 border-b border-border text-sm font-semibold text-text/70">Test History</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Result</th>
                <th className="px-4 py-3">Response Time</th>
                <th className="px-4 py-3">Error</th>
                <th className="px-4 py-3">API Version</th>
                <th className="px-4 py-3">Tested At</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">No test attempts yet.</td></tr>}
              {logs.slice((logsPage - 1) * logsPageSize, (logsPage - 1) * logsPageSize + logsPageSize).map((log) => (
                <tr key={log.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">{log.success ? <span className="text-success">Success</span> : <span className="text-danger">Failure</span>}</td>
                  <td className="px-4 py-3">{log.response_time_ms}ms</td>
                  <td className="px-4 py-3">{log.error_message || "—"}</td>
                  <td className="px-4 py-3">{log.graph_api_version || "—"}</td>
                  <td className="px-4 py-3">{formatISTDateTime(log.tested_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {logs.length > 0 && (
          <div className="px-4 pb-4">
            <Pagination
              page={logsPage}
              totalPages={Math.max(1, Math.ceil(logs.length / logsPageSize))}
              totalItems={logs.length}
              pageSize={logsPageSize}
              itemLabel="test attempts"
              onPageChange={setLogsPage}
              onPageSizeChange={(size) => { setLogsPageSize(size); setLogsPage(1); }}
            />
          </div>
        )}
      </div>
    </SimplePageLayout>
  );
}
