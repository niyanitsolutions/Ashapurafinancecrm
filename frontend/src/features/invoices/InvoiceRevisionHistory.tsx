import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { downloadPdf, getInvoiceRevisions, historicalInvoicePdf, type InvoiceRevision } from "./api";

export function InvoiceRevisionHistory({id, number, version}: {id: string; number: string; version: number}) {
  const [records,setRecords]=useState<InvoiceRevision[]>([]);
  const [error,setError]=useState<string | null>(null);
  const [busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;getInvoiceRevisions(id).then(value=>{if(active)setRecords(value);})
    .catch(e=>{if(active)setError(getErrorMessage(e));});return()=>{active=false;};},[id,version]);
  return <section className="border rounded-xl p-4 mb-4"><h2 className="font-semibold mb-3">Invoice Revision History</h2><ErrorBanner message={error}/>{records.length===0&&<p>No issued revision snapshots available.</p>}<ol className="space-y-3">{records.map(record=><li key={record.revision_number} className="border-l-2 border-primary pl-3"><p>Revision {record.revision_number} {record.current?"(current effective revision)":"(historical)"} - {number}</p><p>{record.reason}</p>{record.approved_by&&<p>Approved by {record.approved_by} on {record.approved_at?new Date(record.approved_at).toLocaleString("en-IN"):"Not recorded"}</p>}<Button variant="secondary" disabled={busy} onClick={async()=>{setBusy(true);setError(null);try{downloadPdf(await historicalInvoicePdf(id,record.revision_number),`${number}-revision-${record.revision_number}.pdf`);}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}}}>Download revision {record.revision_number} PDF</Button></li>)}</ol></section>;
}
