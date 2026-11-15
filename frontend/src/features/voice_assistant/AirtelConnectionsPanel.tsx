import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { getAirtelVoice, saveAirtelVoice, validateAirtelVoice, type AirtelVoiceConnection } from "./airtelApi";

export function AirtelConnectionsPanel() {
  const { isOwner } = usePermissions();
  const { userId } = useAuth();
  const query = useQuery({ queryKey: ["voice", userId, "airtel-voice"], queryFn: getAirtelVoice, enabled: isOwner });
  if (!isOwner) return <p>Airtel VoiceBOT configuration is restricted to the Owner.</p>;
  if (query.error) return <ErrorBanner message={getErrorMessage(query.error)} />;
  if (!query.data) return <p role="status">Loading Airtel VoiceBOT settings…</p>;
  return <AirtelForm key={`${userId}:${query.data.version}`} initial={query.data} />;
}

function AirtelForm({ initial }: { initial: AirtelVoiceConnection }) {
  const { userId } = useAuth();
  const cache = useQueryClient();
  const [origin, setOrigin] = useState(initial.public_origin ?? "");
  const [account, setAccount] = useState(initial.account_sid ?? "");
  const [caller, setCaller] = useState(initial.caller_id ?? "");
  const [flow, setFlow] = useState(initial.call_flow_id ?? "");
  const [capacity, setCapacity] = useState(String(initial.requested_concurrency));
  const [appId, setAppId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [clear, setClear] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = Boolean(appId || apiKey || clear || origin !== (initial.public_origin ?? "") || account !== (initial.account_sid ?? "") || caller !== (initial.caller_id ?? "") || flow !== (initial.call_flow_id ?? "") || capacity !== String(initial.requested_concurrency));
  const fieldClass = "block w-full border rounded-lg p-2";
  return <div className="space-y-5">
    <section className="bg-card border rounded-xl p-5 space-y-2">
      <h2 className="text-lg font-semibold">Airtel IQ — VoiceBOT</h2>
      <p>Configuration: {initial.connection_status} · Provider authentication: {initial.provider_authentication}</p>
      <p>Live calling: disabled · Audio: {initial.audio_status} · Capacity: {initial.capacity_status}</p>
      <p className="text-sm">This connection is separate from Airtel SMS/OTP. Saving settings does not activate calling.</p>
    </section>
    <ErrorBanner message={error} />
    {notice && <p role="status">{notice}</p>}
    <form className="bg-card border rounded-xl p-5 space-y-4" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(null); setNotice(null);
      try {
        await saveAirtelVoice({ version: initial.version, public_origin: origin || null, account_sid: account || null, caller_id: caller || null, call_flow_id: flow || null, requested_concurrency: Number(capacity), clear_credentials: clear, ...(appId ? { app_id: appId } : {}), ...(apiKey ? { api_key: apiKey } : {}) });
        setAppId(""); setApiKey(""); setClear(false);
        setNotice("Airtel VoiceBOT settings saved. Live calling remains disabled.");
        await cache.invalidateQueries({ queryKey: ["voice", userId, "airtel-voice"] });
      } catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>
      <p className="text-sm">HMAC-SHA256 credentials are encrypted on the backend and never returned. Enter both fields to rotate; leave both blank to retain them.</p>
      <label className="block">App ID (write-only)<input className={fieldClass} type="password" autoComplete="new-password" maxLength={256} disabled={clear} value={appId} onChange={e => setAppId(e.target.value)} placeholder={initial.credentials_configured ? "Configured — leave blank to retain" : "Not configured"} /></label>
      <label className="block">API key (write-only)<input className={fieldClass} type="password" autoComplete="new-password" maxLength={4096} disabled={clear} value={apiKey} onChange={e => setApiKey(e.target.value)} /></label>
      <label className="block"><input type="checkbox" checked={clear} onChange={e => { setClear(e.target.checked); if (e.target.checked) { setAppId(""); setApiKey(""); } }} /> Remove both stored credentials</label>
      <label className="block">Public CRM HTTPS origin<input className={fieldClass} type="url" value={origin} onChange={e => setOrigin(e.target.value)} /></label>
      <label className="block">Airtel account SID<input className={fieldClass} maxLength={256} value={account} onChange={e => setAccount(e.target.value)} /></label>
      <label className="block">Approved caller ID<input className={fieldClass} value={caller} onChange={e => setCaller(e.target.value)} /></label>
      <label className="block">Approved call-flow ID<input className={fieldClass} maxLength={256} value={flow} onChange={e => setFlow(e.target.value)} /></label>
      <label className="block">Requested concurrency (planning only)<input className={fieldClass} type="number" min={1} max={500} step={1} required value={capacity} onChange={e => setCapacity(e.target.value)} /></label>
      <Button type="submit" loading={busy} disabled={Boolean(appId) !== Boolean(apiKey)}>Save Airtel VoiceBOT settings</Button>
    </form>
    <section className="bg-card border rounded-xl p-5 space-y-3">
      <h3 className="font-semibold">Documented APIs and registered CRM routes</h3>
      <p className="text-sm">Recording origin: {initial.recording_api_origin}. The click-to-call origin still requires account confirmation.</p>
      <p className="font-mono text-sm break-all">POST {initial.c2c_path}</p>
      <p className="font-mono text-sm break-all">GET {initial.recording_path}</p>
      <p className="text-sm">The routes below are blocked and have not been externally verified. Do not register them with Airtel yet.</p>
      {[["VoiceBOT WebSocket (blocked)", initial.media_url], ["Call events callback (blocked)", initial.events_url], ["CDR callback (blocked)", initial.cdr_url]].map(([label, value]) => <label key={label} className="block text-sm">{label}<input className={`${fieldClass} font-mono`} readOnly value={value ?? "Save a public HTTPS origin to display the route"} /></label>)}
      <p className="text-sm">{initial.webhook_status}</p>
    </section>
    <section className="bg-card border rounded-xl p-5 space-y-3">
      <h3 className="font-semibold">Local validation</h3>
      <p className="text-sm">The guide has no read-only VoiceBOT authentication endpoint. This check sends no network requests and cannot verify credentials, webhook reachability, streaming speech or transfers.</p>
      <Button disabled={busy || dirty || !initial.credentials_configured} onClick={async () => {
        setBusy(true); setError(null);
        try { const evidence = await validateAirtelVoice(); setNotice(evidence.message); await cache.invalidateQueries({ queryKey: ["voice", userId, "airtel-voice"] }); }
        catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
      }}>Validate saved signing and offline codec</Button>
      {dirty && <p className="text-sm">Save changes before validation.</p>}
      {initial.last_test && <p className="text-sm">Last result: {initial.last_test.status} — {initial.last_test.message}</p>}
      <ul className="list-disc pl-5 text-sm space-y-1">{initial.blockers.map(item => <li key={item}>{item}</li>)}</ul>
    </section>
  </div>;
}
