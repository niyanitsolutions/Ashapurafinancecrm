import { Link } from "react-router-dom";
import { useState } from "react";
import { apiRequest } from "@/shared/api/client";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
interface Candidate { id: string; version: number; missing_name: boolean; identity_state: string; matches: {exact: string[]; partial: string[]; truncated: boolean}; preview_fingerprint: string }
interface Preview {items: Candidate[]; counts: Record<string,number>; next_cursor: string | null; has_more: boolean}
export function IdentityReview({onClose,onChanged}: {onClose: () => void; onChanged: () => void}) {
  const [report,setReport] = useState<Preview | null>(null);
  const [selected,setSelected] = useState<Candidate | null>(null);
  const [customer,setCustomer] = useState("");
  const [reason,setReason] = useState("");
  const [confirmed,setConfirmed] = useState(false);
  const [error,setError] = useState<string | null>(null);
  const [busy,setBusy] = useState(false);
  const [last,setLast] = useState<{id: string; version: number; event_id: string} | null>(null);
  async function act(action: () => Promise<void>) { if(busy) return; setBusy(true); setError(null); try { await action(); } catch(e) {setError(e instanceof Error ? e.message : "Review failed.");} finally {setBusy(false);} }
  async function load(after?: string) { const result = await apiRequest<Preview>(`/daily-operations/identity-review/preview?limit=25${after ? `&after=${after}` : ""}`); setReport(result); setSelected(null); }
  return <Modal open title="Owner identity reconciliation" onClose={onClose}>
    <ErrorBanner message={error} />
    <p className="mb-3 text-sm">Preview is read-only. Verify ownership before approving a link. This tool preserves snapshots, applications and history; it cannot merge Customer records. Take a database backup before historical corrections.</p>
    <Button disabled={busy} onClick={() => void act(() => load())}>Generate read-only preview</Button>
    {report && <><p className="my-3 text-sm">Page counts: {Object.entries(report.counts).map(([key,value]) => `${key.replaceAll("_"," ")}: ${value}`).join(" ? ")}</p>
      <ul className="max-h-64 space-y-3 overflow-auto">{report.items.map(row => <li key={row.id} className="rounded border border-border p-2 text-sm"><span className="break-all">Follow-up {row.id}: {row.identity_state}{row.missing_name ? " / missing name" : ""}</span><p>Exact candidates: {row.matches.exact.length}; partial candidates: {row.matches.partial.length}{row.matches.truncated ? " (truncated; narrow review required)" : ""}</p><Button size="sm" variant="secondary" disabled={busy || row.matches.truncated} onClick={() => {setSelected(row);setCustomer("");setReason("");setConfirmed(false);}}>Review candidates</Button></li>)}</ul>
      {report.next_cursor && <Button disabled={busy} variant="secondary" onClick={() => void act(() => load(report.next_cursor!))}>Next preview page</Button>}
    </>}
    {selected && <div className="mt-4 space-y-3"><p className="text-sm">Verify the candidate Customer ID against the existing Customer profile. A partial match requires explicit ownership verification.</p>
      <label className="block text-sm">Verified customer<select className="mt-1 w-full rounded border border-border bg-card p-2" value={customer} onChange={e=>setCustomer(e.target.value)}><option value="">Choose a candidate</option>{[...selected.matches.exact,...selected.matches.partial].map(id=><option key={id} value={id}>{id} ({selected.matches.exact.includes(id) ? "exact" : "partial ? verify"})</option>)}</select></label>
      {customer && <Link className="block text-sm text-primary underline" to={`/customers/${customer}`} target="_blank" rel="noopener noreferrer">View selected customer profile</Link>}
      <label className="block text-sm">Owner decision reason<textarea className="mt-1 w-full rounded border border-border bg-card p-2" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />I verified identity and approve this historical link.</label>
      <Button disabled={busy || !confirmed || !customer || reason.trim().length<5} onClick={() => void act(async()=>{const result=await apiRequest<{id:string;version:number;event_id:string}>(`/daily-operations/identity-review/${selected.id}/link`,{method:"POST",body:JSON.stringify({version:selected.version,customer_id:customer,preview_fingerprint:selected.preview_fingerprint,reason,confirmed:true})});setLast(result);setSelected(null);onChanged();await load();})}>Approve reviewed link</Button>
    </div>}
    {last && <div className="mt-4 space-y-2"><p role="status" className="text-sm">Link recorded with an audit trail. Undo is available while this remains the latest unchanged edit.</p><Button disabled={busy} variant="secondary" onClick={()=>void act(async()=>{await apiRequest(`/daily-operations/identity-review/${last.id}/rollback`,{method:"POST",body:JSON.stringify({version:last.version,event_id:last.event_id,reason:"Owner explicitly reversed the latest reviewed identity link",confirmed:true})});setLast(null);onChanged();await load();})}>Undo last approved link</Button></div>}
  </Modal>;
}
