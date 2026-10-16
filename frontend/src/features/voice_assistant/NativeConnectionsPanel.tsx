import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Badge } from "@/components/badges/Badge";
import { Card, CardHeader } from "@/components/cards/Card";
import { getErrorMessage } from "@/shared/api/errors";
import { getNativeConnections, saveNativeConnection, testNativeConnection, getNativeConnectionEvents, getTelephoneNumbers, saveTelephoneNumber, telephoneNumberAction, type NativeConnection, type TelephoneNumber, type TelephoneNumberInput } from "./api";

const initialNumber: TelephoneNumberInput = { version: 1, number: "", label: "", purpose: "bidirectional", connection_id: null, authorization_reference: null, compliance_reference: null, timezone: "Asia/Kolkata", calling_start: "09:00", calling_end: "18:00", inbound_route: "dynamic_ai" };

export function NativeConnectionsPanel() {
  const { role, userId } = useAuth(); const owner = role === "owner"; const cache = useQueryClient();
  const prefix = ["voice", userId, "native"];
  const [connectionPage, setConnectionPage] = useState(1); const [numberPage, setNumberPage] = useState(1);
  const [editing, setEditing] = useState<NativeConnection | null>(null);
  const [name, setName] = useState(""); const [origin, setOrigin] = useState(""); const [endpoint, setEndpoint] = useState("");
  const [username, setUsername] = useState(""); const [password, setPassword] = useState(""); const [clearCredentials, setClearCredentials] = useState(false);
  const [numberForm, setNumberForm] = useState(initialNumber); const [numberId, setNumberId] = useState<string | undefined>();
  const [reason, setReason] = useState("");
  const connections = useQuery({ queryKey: [...prefix, "connections", connectionPage], queryFn: () => getNativeConnections(connectionPage), enabled: owner });
  const numbers = useQuery({ queryKey: [...prefix, "numbers", numberPage], queryFn: () => getTelephoneNumbers(numberPage), enabled: owner });
  const events = useQuery({ queryKey: [...prefix, "events", editing?.id], queryFn: () => getNativeConnectionEvents(editing!.id), enabled: owner && !!editing });
  const refresh = () => cache.invalidateQueries({ queryKey: prefix });
  const connectionSave = useMutation({ mutationFn: () => saveNativeConnection({ version: editing?.version ?? 1, name, api_origin: origin, endpoint_name: endpoint, ...(username || password ? { username, password } : {}), clear_credentials: clearCredentials }, editing?.id), onSuccess: data => { setEditing(data); setUsername(""); setPassword(""); setClearCredentials(false); void refresh(); } });
  const connectionTest = useMutation({ mutationFn: testNativeConnection, onSuccess: data => { if (editing?.id === data.id) setEditing(data); void refresh(); } });
  const numberSave = useMutation({ mutationFn: () => saveTelephoneNumber(numberForm, numberId), onSuccess: data => { setNumberForm(initialNumber); setNumberId(undefined); setReason(""); void refresh(); return data; } });
  const numberAction = useMutation({ mutationFn: ({ number, action }: { number: TelephoneNumber; action: string }) => telephoneNumberAction(number, action, reason), onSuccess: refresh });
  const busy = connectionSave.isPending || connectionTest.isPending || numberSave.isPending || numberAction.isPending;
  const error = connections.error ?? numbers.error ?? events.error ?? connectionSave.error ?? connectionTest.error ?? numberSave.error ?? numberAction.error;
  const editConnection = (item: NativeConnection | null) => { setEditing(item); setName(item?.name ?? ""); setOrigin(item?.api_origin ?? ""); setEndpoint(item?.endpoint_name ?? ""); setUsername(""); setPassword(""); setClearCredentials(false); connectionSave.reset(); connectionTest.reset(); };
  if (!owner) return <p>Native connections and telephone numbers are restricted to the Owner.</p>;
  return <div className="space-y-5">
    <div className="rounded-[12px] border border-border bg-card p-4"><Badge tone="warning">Live calling disabled</Badge><p className="mt-2 text-sm">Manage your business-controlled PBX connections and approved numbers here. Saving settings or passing a control probe does not verify telecom provisioning, audio or AI readiness. Smartflo remains an optional adapter.</p></div>
    <ErrorBanner message={error ? getErrorMessage(error) : null} />
    <div className="grid gap-5 xl:grid-cols-2">
      <Card><CardHeader title={editing ? "Edit native PBX connection" : "Register native PBX connection"} subtitle="Asterisk ARI · read-only connection verification" action={editing ? <Button variant="ghost" size="sm" onClick={() => editConnection(null)}>New connection</Button> : undefined} />
        {connections.data && !connections.data.origin_allowlist_configured && <p className="mb-4 text-sm text-textSecondary">The operator must configure VOICE_NATIVE_ALLOWED_ORIGINS before any network test can run.</p>}
        <form onSubmit={e => { e.preventDefault(); connectionSave.mutate(); }}>
          <FormField label="Connection name" value={name} required minLength={3} maxLength={80} onChange={e => setName(e.target.value)} />
          <FormField label="PBX API origin" value={origin} type="url" required maxLength={300} placeholder="https://pbx.example.internal:8089" onChange={e => setOrigin(e.target.value)} />
          <FormField label="Configured PJSIP endpoint name" value={endpoint} required pattern="[A-Za-z0-9_.-]+" maxLength={80} onChange={e => setEndpoint(e.target.value)} />
          <FormField label="ARI username (write-only)" value={username} autoComplete="off" maxLength={100} onChange={e => setUsername(e.target.value)} />
          <FormField label="ARI password (write-only)" value={password} type="password" autoComplete="new-password" minLength={8} maxLength={512} onChange={e => setPassword(e.target.value)} />
          <p className="mb-3 text-xs text-textSecondary">Leave both credential fields empty to preserve existing credentials. Use a dedicated read-only ARI user and HTTPS. Credentials stay encrypted on the backend.</p>
          {editing && <label className="mb-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={clearCredentials} onChange={e => setClearCredentials(e.target.checked)} />Remove saved credentials</label>}
          <Button type="submit" disabled={busy}>Save native connection</Button>
        </form>
      </Card>
      <Card><CardHeader title="Connections and verification evidence" subtitle="Checks create no calls and never register or change PBX resources." />
        {connections.isPending && <p role="status">Loading native connections...</p>}
        {connections.data?.items.length === 0 && <p>No native PBX connections registered.</p>}
        {connections.data?.items.map(item => <article key={item.id} className="border-b border-border py-3 space-y-2"><div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{item.name}</h3><Badge tone="neutral">{item.state.replaceAll("_", " ")}</Badge></div><p className="text-sm">{item.api_origin} · {item.endpoint_name}</p><p className="text-xs text-textSecondary">Credentials: {item.credentials_configured ? "configured" : "missing"}. {item.last_test ? `Last control test: ${item.last_test.status}. Calls placed: ${item.last_test.calls_placed}.` : "No connection test recorded."}</p><div className="flex gap-2"><Button size="sm" variant="secondary" disabled={busy} onClick={() => editConnection(item)}>Edit connection</Button><Button size="sm" variant="secondary" disabled={busy || !item.credentials_configured || !connections.data?.origin_allowlist_configured} onClick={() => connectionTest.mutate(item.id)}>Test read-only ARI connection</Button></div></article>)}
        <div className="mt-3 flex items-center gap-3"><Button size="sm" variant="ghost" disabled={connectionPage === 1} onClick={() => setConnectionPage(value => value - 1)}>Previous connections</Button><span className="text-xs">Page {connectionPage}</span><Button size="sm" variant="ghost" disabled={connectionPage * 25 >= (connections.data?.total ?? 0)} onClick={() => setConnectionPage(value => value + 1)}>Next connections</Button></div>
        {editing && <div className="mt-4"><h3 className="font-semibold">Recent control probes</h3>{events.data?.items.length === 0 && <p className="text-sm">No probe events for this connection.</p>}{events.data?.items.map(event => <p className="mt-2 text-xs" key={event.id}>{event.status} · {new Date(event.checked_at).toLocaleString()} · {event.scope}</p>)}</div>}
      </Card>
    </div>
    <Card><CardHeader title={numberId ? "Edit telephone number" : "Register an approved telephone number"} subtitle="Registration stores a draft. The number is never automatically activated." />
      <form onSubmit={e => { e.preventDefault(); numberSave.mutate(); }}>
        <div className="grid gap-x-5 sm:grid-cols-2 xl:grid-cols-3">
          <FormField label="Telephone number (E.164)" type="tel" value={numberForm.number} readOnly={!!numberId} required pattern="\+[1-9][0-9]{7,14}" placeholder="+91..." onChange={e => setNumberForm({ ...numberForm, number: e.target.value })} />
          <FormField label="Number label" value={numberForm.label} required minLength={3} maxLength={80} onChange={e => setNumberForm({ ...numberForm, label: e.target.value })} />
          <SelectField label="Number purpose" value={numberForm.purpose} options={[{ value: "inbound", label: "Inbound" }, { value: "outbound", label: "Outbound" }, { value: "bidirectional", label: "Bidirectional" }]} onChange={e => setNumberForm({ ...numberForm, purpose: e.target.value as TelephoneNumberInput["purpose"] })} />
          <SelectField label="Native connection" value={numberForm.connection_id ?? ""} placeholder="Awaiting connection configuration" options={(connections.data?.items ?? []).map(item => ({ value: item.id, label: item.name }))} onChange={e => setNumberForm({ ...numberForm, connection_id: e.target.value || null })} />
          <FormField label="Telecom authorization reference" value={numberForm.authorization_reference ?? ""} minLength={5} maxLength={150} onChange={e => setNumberForm({ ...numberForm, authorization_reference: e.target.value || null })} />
          <FormField label="Compliance review reference" value={numberForm.compliance_reference ?? ""} minLength={5} maxLength={150} onChange={e => setNumberForm({ ...numberForm, compliance_reference: e.target.value || null })} />
          <FormField label="Number timezone" value={numberForm.timezone} required onChange={e => setNumberForm({ ...numberForm, timezone: e.target.value })} />
          <FormField label="Calling window starts" type="time" value={numberForm.calling_start} required onChange={e => setNumberForm({ ...numberForm, calling_start: e.target.value })} />
          <FormField label="Calling window ends" type="time" value={numberForm.calling_end} required onChange={e => setNumberForm({ ...numberForm, calling_end: e.target.value })} />
        </div><p className="mb-4 text-xs text-textSecondary">Routing target: dynamic AI, subject to verified runtime health and policy. References are Owner attestations; provider approval is not inferred. Never enter credentials or customer information in reference fields.</p>
        <div className="flex gap-2"><Button type="submit" disabled={busy}>Save number draft</Button>{numberId && <Button variant="secondary" disabled={busy} onClick={() => { setNumberId(undefined); setNumberForm(initialNumber); }}>Cancel number edit</Button>}</div>
      </form>
    </Card>
    <Card><CardHeader title="Telephone numbers and activation checklist" subtitle="Every outstanding gate is enforced server-side. Control-only evidence cannot enable calling." />
      {numbers.isPending && <p role="status">Loading telephone numbers...</p>}
      {numbers.data?.items.length === 0 && <p>No telephone numbers registered.</p>}
      <FormField label="Number action reason" value={reason} minLength={5} maxLength={160} onChange={e => setReason(e.target.value)} />
      {numbers.data?.items.map(item => <article key={item.id} className="border-t border-border py-4 space-y-3"><div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">{item.label} · {item.number}</h3><Badge tone="neutral">{item.state.replaceAll("_", " ")}</Badge></div><p className="text-sm">{item.purpose} · {item.timezone} · {item.calling_start}–{item.calling_end} · Live calling disabled</p><ul className="grid gap-2 lg:grid-cols-2">{item.activation_checks.map(check => <li className="text-sm" key={check.key}><span className="font-semibold">{check.passed ? "Recorded" : "Outstanding"}:</span> {check.description}</li>)}</ul><div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy || item.state === "revoked"} onClick={() => { setNumberId(item.id); setNumberForm({ version: item.version, number: item.number, label: item.label, purpose: item.purpose, connection_id: item.connection_id, authorization_reference: item.authorization_reference, compliance_reference: item.compliance_reference, timezone: item.timezone, calling_start: item.calling_start, calling_end: item.calling_end, inbound_route: "dynamic_ai" }); }}>Edit number</Button>{["submit", "review", "suspend", "disable", "reject", "revoke", "activate"].map(action => <Button size="sm" variant={action === "disable" ? "danger" : "secondary"} key={action} disabled={busy || item.state === "revoked" || reason.length < 5 || (action === "activate" && !item.activation_eligible)} onClick={() => numberAction.mutate({ number: item, action })}>{action === "activate" ? "Activate (requirements outstanding)" : action}</Button>)}</div></article>)}
      <div className="mt-3 flex gap-3 items-center"><Button size="sm" variant="ghost" disabled={numberPage === 1} onClick={() => setNumberPage(value => value - 1)}>Previous numbers</Button><span className="text-xs">Page {numberPage}</span><Button size="sm" variant="ghost" disabled={numberPage * 25 >= (numbers.data?.total ?? 0)} onClick={() => setNumberPage(value => value + 1)}>Next numbers</Button></div>
    </Card>
  </div>;
}
