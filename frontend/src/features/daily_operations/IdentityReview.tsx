import { Link } from "react-router-dom";
import { useState } from "react";
import { apiRequest } from "@/shared/api/client";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
interface Candidate { id: string; version: number; missing_name: boolean; identity_state: string; customer_name?:string;customer_number?:string;customer_id?:string;application_id?:string;candidate_details?:{id:string;name:string;mobile:string;code:string;reason:string;applications:{id:string;code:string;status:string;workspace_exists:boolean}[]}[]; matches: {exact: string[]; partial: string[]; truncated: boolean}; preview_fingerprint: string }
interface Preview {items: Candidate[]; counts: Record<string,number>; next_cursor: string | null; has_more: boolean}
export function IdentityReview({onClose,onChanged}: {onClose: () => void; onChanged: () => void}) {
  const [duplicates,setDuplicates]=useState<Record<string,unknown>|null>(null);
  const [report,setReport] = useState<Preview | null>(null);
  const [selected,setSelected] = useState<Candidate | null>(null);
  const [customer,setCustomer] = useState("");
  const [application,setApplication]=useState("");
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
    <Button disabled={busy} variant="secondary" onClick={()=>void act(async()=>setDuplicates(await apiRequest("/daily-operations/identity-review/duplicates")))}>Read-only duplicate report</Button>
    {duplicates && <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(duplicates,null,2)}</pre>}
    {report && <><p className="my-3 text-sm">Page counts: {Object.entries(report.counts).map(([key,value]) => `${key.replaceAll("_"," ")}: ${value}`).join(" ? ")}</p>
      <ul className="max-h-64 space-y-3 overflow-auto">{report.items.map(row => <li key={row.id} className="rounded border border-border p-2 text-sm"><span className="break-all">Follow-up {row.id}: {row.identity_state} ? {row.customer_name} ? {row.customer_number}{row.missing_name ? " / missing name" : ""}</span><p>Exact candidates: {row.matches.exact.length}; partial candidates: {row.matches.partial.length}{row.matches.truncated ? " (truncated; narrow review required)" : ""}</p><Button size="sm" variant="secondary" disabled={busy || row.matches.truncated} onClick={() => {setSelected(row);setCustomer("");setApplication("");setReason("");setConfirmed(false);}}>Review candidates</Button></li>)}</ul>
      {report.next_cursor && <Button disabled={busy} variant="secondary" onClick={() => void act(() => load(report.next_cursor!))}>Next preview page</Button>}
    </>}
    {selected && <div className="mt-4 space-y-3"><p className="text-sm">Verify the candidate Customer ID against the existing Customer profile. A partial match requires explicit ownership verification.</p>
      <label className="block text-sm">Verified customer<select className="mt-1 w-full rounded border border-border bg-card p-2" value={customer} onChange={e=>{setCustomer(e.target.value);setApplication("");setConfirmed(false);}}><option value="">Choose a candidate</option>{[...selected.matches.exact,...selected.matches.partial].map(id=><option key={id} value={id}>{selected.candidate_details?.find(c=>c.id===id)?.code || id} ? {selected.candidate_details?.find(c=>c.id===id)?.name} ({selected.matches.exact.includes(id) ? "exact" : "partial ? verify"})</option>)}</select></label>
      {customer && <Link className="block text-sm text-primary underline" to={`/customers/${customer}`} target="_blank" rel="noopener noreferrer">View selected customer profile</Link>}
      {customer && <><p className="text-sm">{selected.candidate_details?.find(c=>c.id===customer)?.reason} ? {selected.candidate_details?.find(c=>c.id===customer)?.mobile}</p><label className="block text-sm">Verified Application (required when applications exist)<select className="mt-1 w-full rounded border border-border bg-card p-2" value={application} onChange={e=>{setApplication(e.target.value);setConfirmed(false);}}><option value="">No Application selected</option>{selected.candidate_details?.find(c=>c.id===customer)?.applications.map(a=><option key={a.id} value={a.id} disabled={a.workspace_exists}>{a.code} ? {a.status}{a.workspace_exists?" ? workspace exists; cannot merge":""}</option>)}</select></label></>}
      <label className="block text-sm">Owner decision reason<textarea className="mt-1 w-full rounded border border-border bg-card p-2" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />I verified identity and approve this historical link.</label>
      <Button disabled={busy || !confirmed || !customer || reason.trim().length<5} onClick={() => void act(async()=>{const result=await apiRequest<{id:string;version:number;event_id:string}>(`/daily-operations/identity-review/${selected.id}/link`,{method:"POST",body:JSON.stringify({version:selected.version,customer_id:customer,application_id:application||null,preview_fingerprint:selected.preview_fingerprint,reason,confirmed:true})});setLast(result);setSelected(null);onChanged();await load();})}>Approve reviewed link</Button>
    </div>}
    {selected && <div className="mt-3 flex flex-wrap gap-2">{(["reject_suggestion","leave_standalone","manual_review"] as const).map(decision=><Button key={decision} variant="secondary" disabled={busy||reason.trim().length<5} onClick={()=>void act(async()=>{await apiRequest(`/daily-operations/identity-review/${selected.id}/decision`,{method:"POST",body:JSON.stringify({version:selected.version,decision,reason})});setSelected(null);onChanged();await load();})}>{decision==="reject_suggestion"?"Reject suggestion":decision==="leave_standalone"?"Leave standalone":"Record need for manual review"}</Button>)}</div>}
    {last && <div className="mt-4 space-y-2"><p role="status" className="text-sm">Link recorded with an audit trail. Undo is available while this remains the latest unchanged edit.</p><Button disabled={busy} variant="secondary" onClick={()=>void act(async()=>{await apiRequest(`/daily-operations/identity-review/${last.id}/rollback`,{method:"POST",body:JSON.stringify({version:last.version,event_id:last.event_id,reason:"Owner explicitly reversed the latest reviewed identity link",confirmed:true})});setLast(null);onChanged();await load();})}>Undo last approved link</Button></div>}
  </Modal>;
}
