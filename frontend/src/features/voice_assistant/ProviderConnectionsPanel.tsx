import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { getSmartfloConnection, getSmartfloEvents, saveSmartfloConnection, testSmartflo, type SmartfloConnection } from "./api";

export function ProviderConnectionsPanel() {
  const { isOwner } = usePermissions(); const { userId } = useAuth();
  const query = useQuery({ queryKey: ["voice", userId, "smartflo", "connection"], queryFn: getSmartfloConnection, enabled: isOwner });
  if (!isOwner) return <p>Provider credentials, tests and event logs are restricted to the Owner.</p>;
  if (query.error) return <ErrorBanner message={getErrorMessage(query.error)} />;
  if (!query.data) return <p role="status">Loading Smartflo connection settings…</p>;
  return <ConnectionForm key={`${userId}:${query.data.version}`} initial={query.data} />;
}

function ConnectionForm({ initial }: { initial: SmartfloConnection }) {
  const { userId } = useAuth(); const client = useQueryClient();
  const [origin, setOrigin] = useState(initial.public_origin ?? "");
  const [apiToken, setApiToken] = useState(""); const [callbackToken, setCallbackToken] = useState("");
  const [clearApi, setClearApi] = useState(false); const [clearCallback, setClearCallback] = useState(false);
  const [mode, setMode] = useState(initial.callback_mode); const [expiry, setExpiry] = useState(initial.token_expires_at ?? "");
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null); const [page, setPage] = useState(1);
  const events = useQuery({ queryKey: ["voice", userId, "smartflo", "events", page], queryFn: () => getSmartfloEvents(page), refetchInterval: 15000 });
  const dirty = !!apiToken || !!callbackToken || clearApi || clearCallback || origin !== (initial.public_origin ?? "") || expiry !== (initial.token_expires_at ?? "") || mode !== initial.callback_mode;
  async function run(kind: "connection" | "webhook" | "audio") {
    setBusy(true); setError(null); setNotice(null);
    try { const result = await testSmartflo(kind); setNotice(`${result.status}: ${result.message}`); await client.invalidateQueries({ queryKey: ["voice", userId, "smartflo"] }); }
    catch (e) { setError(getErrorMessage(e)); } finally { setBusy(false); }
  }
  const urls = [
    ["Incoming call webhook URL", initial.incoming_webhook_url],
    ["Answered event webhook URL", initial.answered_webhook_url],
    ["Call status webhook URL", initial.call_status_webhook_url],
    ["Dynamic audio endpoint URL (blocked)", initial.dynamic_endpoint_url],
    ["Audio WebSocket URL (blocked)", initial.audio_websocket_url],
  ];
  return <div className="space-y-6">
    <section className="bg-card border rounded-xl p-5 space-y-2"><h2 className="text-lg font-semibold">Tata Tele Business — Smartflo</h2>
      <p>API: {initial.connection_status} · Sandbox: {initial.sandbox}</p><p>Audio: {initial.audio_status} · Live calling: disabled</p>
      {initial.last_test && <p className="text-sm">Last API test: {new Date(initial.last_test.tested_at).toLocaleString()} — {initial.last_test.message}</p>}
      {initial.token_expired && <p className="text-danger">Configured token expiry has passed.</p>}
    </section>
    <ErrorBanner message={error} />{notice && <p role="status" className="bg-primary/10 p-4 rounded-xl">{notice}</p>}
    <form className="bg-card border rounded-xl p-5 space-y-4" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(null); setNotice(null);
      try { await saveSmartfloConnection({ version: initial.version, api_base_url: initial.api_base_url, public_origin: origin || null,
        ...(apiToken ? { api_token: apiToken } : {}), ...(callbackToken ? { callback_token: callbackToken } : {}),
        clear_api_token: clearApi, clear_callback_token: clearCallback, callback_mode: mode, token_expires_at: expiry || null });
        setApiToken(""); setCallbackToken(""); setNotice("Connection settings saved. Live calling remains disabled."); await client.invalidateQueries({ queryKey: ["voice", userId, "smartflo"] });
      } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>
      <label className="block">API base URL<input readOnly className="block w-full border rounded-lg p-2 font-mono text-sm" value={initial.api_base_url} /></label>
      <p className="text-sm text-text/70">API authentication uses a server-side Bearer token. Secrets are encrypted, write-only and never stored in browser storage.</p>
      <label className="block">API token (write-only)<input type="password" autoComplete="new-password" minLength={20} maxLength={4096} disabled={clearApi} className="block w-full border rounded-lg p-2" value={apiToken} onChange={e => setApiToken(e.target.value)} placeholder={initial.api_token_configured ? "Configured — leave blank to keep" : "Not configured"} /></label>
      <label className="block"><input type="checkbox" checked={clearApi} onChange={e => { setClearApi(e.target.checked); if (e.target.checked) setApiToken(""); }} /> Remove stored API token</label>
      <label className="block">Token expiry (ISO 8601 with offset)<input className="block w-full border rounded-lg p-2" value={expiry} onChange={e => setExpiry(e.target.value)} placeholder="Optional: YYYY-MM-DDTHH:mm:ssZ" /></label>
      <label className="block">Deployed CRM public HTTPS origin<input type="url" className="block w-full border rounded-lg p-2" value={origin} onChange={e => setOrigin(e.target.value)} placeholder="Enter deployed HTTPS origin without a path" /></label>
      <label className="block">Callback authentication token (write-only)<input type="password" autoComplete="new-password" minLength={32} maxLength={256} disabled={clearCallback} className="block w-full border rounded-lg p-2" value={callbackToken} onChange={e => setCallbackToken(e.target.value)} placeholder={initial.callback_token_configured ? "Configured — leave blank to keep" : "Separate random token, at least 32 characters"} /></label>
      <label className="block"><input type="checkbox" checked={clearCallback} onChange={e => { setClearCallback(e.target.checked); if (e.target.checked) setCallbackToken(""); }} /> Remove stored callback token</label>
      <label className="block">Callback ingestion<select className="block border rounded-lg p-2" value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="disabled">Disabled</option><option value="validation_only">Validation observations only — cannot control calls</option></select></label>
      <Button type="submit" loading={busy}>Save connection settings</Button>
    </form>
    <section className="bg-card border rounded-xl p-5 space-y-3"><h3 className="font-semibold">Webhook and audio endpoints</h3><p className="text-sm">URL deployment status: {initial.url_verification}. These backend routes do not prove DNS, TLS or provider reachability. Do not register blocked audio endpoints.</p>
      {urls.map(([label, value]) => <label key={label} className="block text-sm">{label}<input readOnly className="block w-full border rounded-lg p-2 font-mono" value={value ?? "Save a verified HTTPS origin to generate this URL"} /></label>)}
      <p className="text-sm">Configure JSON POST, UTC ISO timestamps and a separate Authorization Bearer callback header. Confirm header delivery in Smartflo’s account request preview. No provider HMAC signature is assumed.</p>
      <p className="text-sm">Smartflo tokens created before 9 August 2026 expire on 31 October 2026. Replace legacy credentials and record the actual provider expiry. <a className="underline" href="https://docs.smartflo.tatatelebusiness.com/docs/api-token" target="_blank" rel="noreferrer">Official token documentation</a></p>
    </section>
    <section className="bg-card border rounded-xl p-5 space-y-3"><h3 className="font-semibold">Connection tests</h3>{dirty && <p className="text-sm">Save configuration changes before testing credentials or callbacks.</p>}<div className="flex flex-wrap gap-3">
      <Button disabled={busy || dirty || !initial.api_token_configured || initial.token_expired} onClick={() => run("connection")}>Test API connection (read-only)</Button>
      <Button variant="secondary" disabled={busy || dirty || !initial.callback_token_configured} onClick={() => run("webhook")}>Test local webhook pipeline</Button>
      <Button variant="secondary" disabled={busy} onClick={() => run("audio")}>Test offline audio protocol</Button>
    </div><p className="text-sm">External webhook delivery, streaming speech, interruptions and transfers require provider sandbox testing.</p>{initial.warnings.map(warning => <p key={warning} className="text-sm text-text/70">{warning}</p>)}</section>
    <section className="bg-card border rounded-xl p-5 space-y-3"><h3 className="font-semibold">Provider event observations · 30-day retention</h3><ErrorBanner message={events.error ? getErrorMessage(events.error) : null} />
      {events.isPending ? <p role="status">Loading provider events…</p> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><th className="text-left p-2">Trigger</th><th className="text-left p-2">Provider reference</th><th className="text-left p-2">Processing</th><th className="text-left p-2">Received</th></tr></thead><tbody>{events.data?.items.map((event, i) => <tr className="border-t" key={`${event.provider_call_id}-${i}`}><td className="p-2">{event.trigger}</td><td className="p-2">{event.provider_call_id}</td><td className="p-2">{event.status}</td><td className="p-2">{new Date(event.received_at).toLocaleString()}</td></tr>)}</tbody></table>{!events.data?.items.length && <p>No provider events received.</p>}</div>}
      <div className="flex gap-3 items-center"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page}</span><Button variant="secondary" disabled={page * 25 >= (events.data?.total ?? 0)} onClick={() => setPage(p => p + 1)}>Next</Button></div>
    </section>
  </div>;
}
