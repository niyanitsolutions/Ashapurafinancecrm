import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/shared/api/errors";
import { downloadPdf, duplicateInvoice, invoicePdf, listInvoices, money, setInvoiceStatus, type Invoice } from "./api";

export function InvoiceListPage() {
  const {can} = usePermissions();
  const navigate = useNavigate();
  const [cancel,setCancel] = useState<Invoice | null>(null); const [reason,setReason] = useState("");
  const [busy,setBusy] = useState(false); const [revision,setRevision] = useState(0);
  const [printBlob,setPrintBlob] = useState<Blob | null>(null); const [printUrl,setPrintUrl] = useState("");
  const [search,setSearch] = useState(""); const [status,setStatus] = useState("");
  const [from,setFrom] = useState(""); const [to,setTo] = useState("");
  const [sort,setSort] = useState("created_at"); const [page,setPage] = useState(1);
  const [data,setData] = useState<{items: Invoice[]; total: number; total_pages: number} | null>(null);
  const [error,setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true; setData(null); setError(null);
    const timer = setTimeout(() => {
      const q = new URLSearchParams({search,status,sort,page: String(page)});
      if (from) q.set("from_date",from); if (to) q.set("to_date",to);
      listInvoices(q).then(v => {if(active) {setData(v);if(page>Math.max(1,v.total_pages))setPage(Math.max(1,v.total_pages));}}).catch(e => {if(active) setError(getErrorMessage(e));});
    },200);
    return () => {active=false; clearTimeout(timer);};
  },[search,status,from,to,sort,page,revision]);
  useEffect(()=>{if(!printBlob)return;const url=URL.createObjectURL(printBlob);setPrintUrl(url);return()=>URL.revokeObjectURL(url);},[printBlob]);
  async function act(row: Invoice, action: string) {
    setError(null);setBusy(true);
    try {
      if(action==="download") downloadPdf(await invoicePdf(row.id,"download"),`${row.invoice_number}.pdf`);
      if(action==="print") setPrintBlob(await invoicePdf(row.id,"print"));
      if(action==="duplicate") {const copy=await duplicateInvoice(row.id);navigate(`/invoices/${copy.id}/edit`);}
      if(action==="cancel") {setCancel(row);setReason("");}
    } catch(e) {setError(getErrorMessage(e));} finally {setBusy(false);}
  }
  return <SimplePageLayout title="Invoices" subtitle="Finance / Billing" actions={can("invoices:invoices","create") && <Link className="text-primary font-semibold" to="/invoices/new">Create invoice</Link>}>
    <ErrorBanner message={error}/>
    {cancel&&<form className="border rounded-xl bg-card p-4 mb-4" onSubmit={async e=>{e.preventDefault();setBusy(true);try{await setInvoiceStatus(cancel.id,"cancelled",cancel.version,reason);setCancel(null);setRevision(v=>v+1);}catch(err){setError(getErrorMessage(err));}finally{setBusy(false);}}}>
      <label>Cancellation reason for {cancel.invoice_number}<textarea required maxLength={500} className="block border rounded-lg p-2 w-full my-3" value={reason} onChange={e=>setReason(e.target.value)}/></label><Button type="submit" variant="danger" disabled={busy}>Confirm cancellation</Button><Button variant="ghost" onClick={()=>setCancel(null)}>Keep invoice</Button>
    </form>}
    {printUrl&&<iframe title="Print invoice" className="fixed w-0 h-0 border-0" src={printUrl} onLoad={e=>{e.currentTarget.contentWindow?.focus();e.currentTarget.contentWindow?.print();}}/>}
    <div className="flex flex-wrap gap-3 mb-5">
      <input className="border rounded-lg p-2" aria-label="Search invoices" placeholder="Invoice number or customer" value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}}/>
      <select className="border rounded-lg p-2" aria-label="Status filter" value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}>
        <option value="">All statuses</option>{["draft","issued","partially_paid","paid","cancelled"].map(s=><option key={s}>{s}</option>)}
      </select>
      <label>From <input className="border rounded-lg p-2" type="date" value={from} onChange={e=>{setFrom(e.target.value);setPage(1);}}/></label>
      <label>To <input className="border rounded-lg p-2" type="date" value={to} onChange={e=>{setTo(e.target.value);setPage(1);}}/></label>
      <select className="border rounded-lg p-2" aria-label="Sort invoices" value={sort} onChange={e=>setSort(e.target.value)}>
        <option value="created_at">Newest created</option><option value="invoice_date">Invoice date</option><option value="invoice_number">Invoice number</option><option value="customer.name">Customer</option>
      </select>
    </div>
    <div className="overflow-x-auto bg-card border rounded-xl">
      <table className="w-full text-sm text-left whitespace-nowrap"><thead className="bg-background"><tr>{["Invoice No.","Customer / Company","Invoice Date","Due Date","GSTIN","Taxable","GST","Grand Total","Status","Created By","Created Date","Actions"].map(h=><th className="p-3" key={h}>{h}</th>)}</tr></thead>
        <tbody>{data?.items.map(row=><tr className="border-t" key={row.id}>
          <td className="p-3"><Link className="text-primary" to={`/invoices/${row.id}`}>{row.invoice_number}</Link></td>
          <td className="p-3">{row.customer.name}</td><td className="p-3">{row.invoice_date}</td><td className="p-3">{row.due_date}</td><td className="p-3">{row.customer.gstin || "—"}</td>
          <td className="p-3">{money(row.subtotal)}</td><td className="p-3">{money(row.gst_total)}</td><td className="p-3 font-semibold">{money(row.grand_total)}</td><td className="p-3">{row.status.replaceAll("_"," ")}</td>
          <td className="p-3">{row.created_by_name}</td><td className="p-3">{new Date(row.created_at).toLocaleDateString("en-IN")}</td>
          <td className="p-3"><Link className="text-primary" to={`/invoices/${row.id}`}>View</Link>{row.status === "draft" && can("invoices:invoices","edit") && <Link className="ml-3 text-primary" to={`/invoices/${row.id}/edit`}>Edit</Link>}
            <select aria-label={`Actions for ${row.invoice_number}`} value="" disabled={busy} className="ml-3 border rounded-lg p-2" onChange={e=>void act(row,e.target.value)}><option value="">Actions</option><option value="download">Download PDF</option><option value="print">Print</option>{can("invoices:invoices","create")&&<option value="duplicate">Duplicate</option>}{can("invoices:invoices","edit")&&["draft","issued","partially_paid"].includes(row.status)&&<option value="cancel">Cancel</option>}</select>
          </td>
        </tr>)}</tbody></table>
      {!data && !error && <p className="p-5">Loading invoices…</p>}
      {data?.items.length === 0 && <p className="p-5">No invoices found.</p>}
    </div>
    <div className="flex items-center gap-4 mt-4"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(page-1)}>Previous</Button>
      <span>Page {page} of {Math.max(1,data?.total_pages ?? 1)} · {data?.total ?? 0} invoices</span><Button variant="secondary" disabled={!data || page>=data.total_pages} onClick={()=>setPage(page+1)}>Next</Button></div>
  </SimplePageLayout>;
}
