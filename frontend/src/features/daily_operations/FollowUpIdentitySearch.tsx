import { useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { apiRequest } from "@/shared/api/client";
import { base, type Row } from "./api";

interface Choice { entity: "application" | "lead" | "customer"; id: string; code: string; customer_name: string; mobile: string; customer_code?: string; product?: string; status?: string; assigned_to_name?: string; workspace_status: string }
export function FollowUpIdentitySearch({ onClose, onSelected, onStandalone }: { onClose: () => void; onSelected: (record: Row) => void; onStandalone: (identity?:Record<string,string>) => void }) {
  const [customer,setCustomer]=useState<Choice|null>(null);
  const [reason,setReason]=useState("");
  const [confirmed,setConfirmed]=useState(false);
  const [query,setQuery]=useState("");
  const [result,setResult]=useState<{items:Choice[];has_more:boolean}|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  async function run(action:()=>Promise<void>) {if(lock.current)return;lock.current=true;setBusy(true);setError(null);try{await action();}catch(e){setError(e instanceof Error?e.message:"Identity search failed.");}finally{lock.current=false;setBusy(false);}}
  return <Modal open title="Add Daily Follow-up" onClose={()=>{if(!busy)onClose();}} size="lg">
    <p className="mb-3 text-sm">Search existing Customer / Application / Lead first. Select the intended application to keep its activities in one workspace. Matching names or mobile numbers never link records automatically.</p>
    <ErrorBanner message={error}/>
    <form onSubmit={e=>{e.preventDefault();void run(async()=>setResult(await apiRequest(`${base}/follow-up-identities?search=${encodeURIComponent(query.trim())}`)));}}>
      <FormField label="Customer name, mobile, Customer ID, Application ID or Lead code" value={query} minLength={2} maxLength={120} required disabled={busy} onChange={e=>{setQuery(e.target.value);setResult(null);setCustomer(null);}}/>
      <Button type="submit" disabled={busy||query.trim().length<2}>Search existing identities</Button>
    </form>
    {result && <div className="mt-4 space-y-3">
      {!result.items.length && <p>No authorized matches found. Server validation also checks for identity conflicts before saving.</p>}
      {result.has_more && <p role="status">More matches exist. Narrow your search using an exact ID or mobile number.</p>}
      {result.items.map(choice=><div className="rounded-lg border border-border p-3 text-sm" key={`${choice.entity}:${choice.id}`}>
        <p className="font-semibold">{choice.code} · {choice.customer_name}</p>
        <p>{[choice.mobile,choice.customer_code,choice.product,choice.status,choice.assigned_to_name].filter(Boolean).join(" · ")}</p>
        <p>{choice.workspace_status}</p>
        {choice.entity!=="customer" ? <Button size="sm" disabled={busy||choice.workspace_status==="Owner review required"} onClick={()=>void run(async()=>onSelected(await apiRequest<Row>(`${base}/linked-follow-up`,{method:"POST",body:JSON.stringify({entity:choice.entity,record_id:choice.id})})))}>Open workspace</Button> : <><a className="text-primary underline" href={`/customers/${choice.id}`} target="_blank" rel="noopener noreferrer">View customer for identity review</a><Button size="sm" disabled={busy} onClick={()=>{setCustomer(choice);setReason("");setConfirmed(false);}}>Review Customer without an Application</Button></>}
      </div>)}
      {customer && <section className="rounded-lg border border-border p-3"><p className="text-sm">Verify {customer.code} and {customer.customer_name} before linking this follow-up to the Customer. No Application will be created.</p><FormField label="Owner identity verification reason" value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)}/><label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I verified this Customer relationship.</label><Button disabled={busy||!confirmed||reason.trim().length<5} onClick={()=>onStandalone({customer_name:customer.customer_name,customer_number:customer.mobile,review_customer_id:customer.id,identity_review_reason:reason})}>Continue with verified Customer</Button></section>}
      <p className="text-sm">For a genuinely new prospect with no verified CRM relationship, create a standalone record. Conflicting identities require Owner review.</p>
      <Button variant="secondary" disabled={busy} onClick={()=>onStandalone()}>Create Standalone / Unlinked record</Button>
    </div>}
  </Modal>;
}
