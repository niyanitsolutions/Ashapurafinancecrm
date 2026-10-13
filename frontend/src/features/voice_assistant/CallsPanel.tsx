import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/shared/api/errors";
import { callAction, getCall, getCalls, simulateCall } from "./api";

const terminal = ["completed", "missed", "failed", "cancelled"];
export function CallsPanel({ direction = "", live = false }: { direction?: string; live?: boolean }) {
  const { userId } = useAuth();
  const { can } = usePermissions();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [label, setLabel] = useState("Test caller");
  const [consent, setConsent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const effectiveStatus = live && !status ? "active" : status;
  const calls = useQuery({ queryKey: ["voice", userId, "calls", page, effectiveStatus, direction], queryFn: () => getCalls(page, effectiveStatus, direction), refetchInterval: 5000 });
  const detail = useQuery({ queryKey: ["voice", userId, "call", selected], queryFn: () => getCall(selected!), enabled: !!selected, refetchInterval: 3000 });
  async function action(name: string) {
    if (!detail.data) return;
    setBusy(true); setError(null);
    try { await callAction(detail.data, name); await client.invalidateQueries({ queryKey: ["voice", userId] }); }
    catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  }
  const rows = (calls.data?.items ?? []).filter(call => !live || !terminal.includes(call.status));
  return <div className="space-y-5">
    <p className="text-sm text-text/70">Mock sessions only. No telephone or browser audio is connected. Status refreshes every 5 seconds while this page is open.</p>
    <ErrorBanner message={error ?? (calls.error ? getErrorMessage(calls.error) : detail.error ? getErrorMessage(detail.error) : null)} />
    {direction && can("voice_assistant:calls", "create") && <form className="flex flex-wrap gap-3 items-end bg-card p-4 rounded-xl border" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError(null);
      try { const call = await simulateCall(direction, label, consent, key); setKey(crypto.randomUUID()); setSelected(call.id); await client.invalidateQueries({ queryKey: ["voice", userId] }); }
      catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
    }}>
      <label>Test caller label<input className="block border rounded-lg p-2" required maxLength={80} value={label} onChange={e => setLabel(e.target.value)} /></label>
      {direction === "outgoing" && <label>Test consent evidence reference<input className="block border rounded-lg p-2" required minLength={5} maxLength={150} value={consent} onChange={e => setConsent(e.target.value)} /></label>}
      <Button type="submit" loading={busy}>Simulate {direction} call</Button>
    </form>}
    <label>Call status<select className="border rounded-lg p-2 ml-3" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">{live ? "All active statuses" : "All statuses"}</option>{["ringing", "ai_active", "human_active", "transferring", ...(live ? [] : terminal)].map(s => <option key={s}>{s}</option>)}</select></label>
    {calls.isPending ? <p role="status">Loading calls…</p> : <div className="overflow-x-auto bg-card border rounded-xl"><table className="w-full text-sm"><thead><tr>{["Caller", "Direction", "Status", "Created", "Duration", "Details"].map(t => <th className="p-3 text-left" key={t}>{t}</th>)}</tr></thead><tbody>{rows.map(call => <tr className="border-t" key={call.id}><td className="p-3">{call.contact_label}</td><td>{call.direction}</td><td>{call.status}</td><td>{new Date(call.created_at).toLocaleString()}</td><td>{call.duration_seconds}s</td><td><Button variant="ghost" onClick={() => setSelected(call.id)}>Open</Button></td></tr>)}</tbody></table>{!rows.length && <p className="p-5">No matching calls on this page.</p>}</div>}
    <div className="flex gap-3 items-center"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button><span>Page {page} · {calls.data?.total ?? 0} records</span><Button variant="secondary" disabled={page >= (calls.data?.total_pages ?? 1)} onClick={() => setPage(p => p + 1)}>Next</Button></div>
    {detail.data && <section className="bg-card p-5 rounded-xl border space-y-3" aria-label="Call detail">
      <div className="flex justify-between"><h2 className="font-semibold">{detail.data.contact_label} · {detail.data.status}</h2><Button variant="ghost" onClick={() => setSelected(null)}>Close</Button></div>
      <p>Recording: disabled · Transfer: {detail.data.transfer_outcome ?? "none"}</p>
      <p className="text-sm">Current deadline: {new Date(detail.data.deadline_at).toLocaleString()}</p>
      {can("voice_assistant:calls", "edit") && <div className="flex gap-2 flex-wrap">
        {detail.data.status === "ringing" && <><Button disabled={busy} onClick={() => action("answer")}>Simulate human answer</Button><Button variant="secondary" disabled={busy} onClick={() => action("reject")}>Reject / fallback</Button></>}
        {detail.data.status === "ai_active" && <Button disabled={busy} onClick={() => action("transfer")}>Request mock transfer</Button>}
        {detail.data.status === "transferring" && <><Button disabled={busy} onClick={() => action("transfer_confirmed")}>Simulate provider confirmation</Button><Button variant="secondary" disabled={busy} onClick={() => action("transfer_failed")}>Simulate transfer failure</Button></>}
        {!terminal.includes(detail.data.status) && <Button variant="danger" disabled={busy} onClick={() => action("end")}>End simulation</Button>}
      </div>}
      <ol className="space-y-2">{detail.data.timeline.map((event, i) => <li key={i} className="border-l-2 border-primary pl-3">{event.state} — {new Date(event.at).toLocaleString()}<span className="block text-xs text-text/60">{event.reason}</span></li>)}</ol>
    </section>}
  </div>;
}
