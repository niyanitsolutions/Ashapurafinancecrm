import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/shared/api/errors";
import { downloadPdf, getInvoice, invoicePdf, setInvoiceStatus, type Invoice, type Status } from "./api";

import { InvoiceWorkflow, InvoiceReference, type Workflow } from "./InvoiceWorkflow";

export function InvoiceViewPage() {
  const navigate=useNavigate();
  const {invoiceId=""}=useParams();const {can}=usePermissions();
  const [workflow,setWorkflow]=useState<Workflow | null>(null);
  const [invoice,setInvoice]=useState<Invoice | null>(null);const [error,setError]=useState<string | null>(null);
  const [url,setUrl]=useState("");const [blob,setBlob]=useState<Blob | null>(null);const [busy,setBusy]=useState(false);
  const [cancel,setCancel]=useState(false);const [reason,setReason]=useState("");const frame=useRef<HTMLIFrameElement>(null);
  useEffect(()=>{let active=true;setInvoice(null);setBlob(null);setError(null);
    getInvoice(invoiceId).then(v=>{if(active)setInvoice(v);}).catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};
  },[invoiceId]);
  useEffect(()=>{if(!invoice)return;let active=true;invoicePdf(invoice.id).then(b=>{if(active)setBlob(b);}).catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};},[invoice]);
  useEffect(()=>{if(!blob){setUrl("");return;}const next=URL.createObjectURL(blob);setUrl(next);return()=>URL.revokeObjectURL(next);},[blob]);
  async function action(fn: ()=>Promise<void>) {setBusy(true);setError(null);try{await fn();}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}
  const status=(next: Status)=>action(async()=>{if(invoice){setInvoice(await setInvoiceStatus(invoiceId,next,invoice.version,reason));setCancel(false);}});
  return <SimplePageLayout title={invoice?.invoice_number??"Invoice"} backTo="/invoices" subtitle={invoice?.status.replaceAll("_"," ")} actions={<>
    {!invoice?.is_archived&&invoice?.status==="draft"&&can("invoices:invoices","edit")&&<Link className="text-primary" to={`/invoices/${invoiceId}/edit`}>Edit</Link>}
    <Button variant="secondary" disabled={busy||!invoice} onClick={()=>void action(async()=>downloadPdf(await invoicePdf(invoiceId,"download"),`${invoice?.invoice_number}.pdf`))}>Download PDF</Button>
    <Button variant="secondary" disabled={busy||!url} onClick={()=>void action(async()=>{await invoicePdf(invoiceId,"print");frame.current?.contentWindow?.focus();frame.current?.contentWindow?.print();})}>Print</Button>
    {invoice&&!invoice.is_archived&&!["paid","partially_paid"].includes(invoice.status)&&can("invoices:invoices","create")&&<Button variant="secondary" disabled={busy||!invoice} onClick={()=>setWorkflow("duplicate")}>Duplicate</Button>}
  </>}>
    <ErrorBanner message={error}/>
    {invoice && <><InvoiceReference invoice={invoice}/><div className="flex flex-wrap gap-3 mb-4"><Button variant="secondary" onClick={()=>setWorkflow("history")}>View History</Button>{!invoice.is_archived&&invoice.status!=="draft"&&can("invoices:invoices","edit")&&<Button variant="secondary" onClick={()=>setWorkflow("archive")}>Archive</Button>}{!invoice.is_archived&&invoice.status==="draft"&&can("invoices:invoices","edit")&&<Button variant="danger" onClick={()=>setWorkflow("delete")}>Delete</Button>}{!invoice.is_archived&&["issued","cancelled"].includes(invoice.status)&&can("invoices:invoices","create")&&can("invoices:invoices","edit")&&<Button onClick={()=>setWorkflow("replacement")}>Create Correction / Replacement</Button>}</div>{workflow&&<InvoiceWorkflow key={`${invoice.id}-${workflow}`} invoice={invoice} mode={workflow} onClose={()=>setWorkflow(null)} onDeleted={message=>{navigate("/invoices", {state:{invoiceNotice:message}});}}/>}</>}

    {invoice&&!invoice.is_archived&&can("invoices:invoices","edit")&&<div className="flex flex-wrap gap-3 mb-4">
      {!invoice.is_archived&&invoice.status==="draft"&&<Button disabled={busy} onClick={()=>void status("issued")}>Issue invoice</Button>}
      {["issued","partially_paid"].includes(invoice.status)&&<Button disabled={busy} onClick={()=>void status("paid")}>Mark paid</Button>}
      {invoice.status==="issued"&&<Button variant="secondary" disabled={busy} onClick={()=>void status("partially_paid")}>Mark partially paid</Button>}
      {["draft","issued"].includes(invoice.status)&&<Button variant="danger" disabled={busy} onClick={()=>setCancel(true)}>Cancel invoice</Button>}
    </div>}
    {invoice?.number_reused_from&&<p className="mb-4">Invoice number {invoice.invoice_number} was allocated from the latest eligible deleted draft. The previous draft remains in audit history.</p>}
    {invoice?.is_archived&&<p className="mb-4">Archived: {invoice.archive_reason}. Invoice status and reserved number are unchanged.</p>}
    {invoice?.cancellation_reason&&<p className="mb-4">Cancellation reason: {invoice.cancellation_reason}</p>}
    {cancel&&<form className="border rounded-xl p-4 mb-4" onSubmit={e=>{e.preventDefault();void status("cancelled");}}><label>Cancellation reason<textarea className="block w-full border rounded-lg p-2 mt-2" required maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="flex gap-3 mt-3"><Button variant="danger" type="submit" disabled={busy}>Confirm cancellation</Button><Button variant="secondary" onClick={()=>setCancel(false)}>Keep invoice</Button></div></form>}
    {url?<iframe ref={frame} title="Invoice PDF" src={url} className="w-full h-[1050px] border rounded-xl bg-white"/>:!error&&<p>Loading invoice preview…</p>}
  </SimplePageLayout>;
}
