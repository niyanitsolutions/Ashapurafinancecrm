import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { archiveInvoice, deleteInvoice, duplicateInvoice, getCorrectionDraft, getDeleteOptions, invoiceHistory, replacementInvoice, type Invoice, type InvoiceEvent } from "./api";

export type Workflow = "delete" | "duplicate" | "replacement" | "history" | "archive";
export function InvoiceWorkflow({invoice, mode, onClose, onDeleted}: {
  invoice: Invoice; mode: Workflow; onClose: () => void; onDeleted: (message?: string) => void;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [events, setEvents] = useState<InvoiceEvent[] | null>(null);
  const [existing, setExisting] = useState<Invoice | null>(null);
  const [checked, setChecked] = useState(mode !== "replacement" && mode !== "delete");
  const [eligibility, setEligibility] = useState<string>("Checking number eligibility?");
  const [revision, setRevision] = useState(false);
  const key = useRef(crypto.randomUUID());
  useEffect(() => {
    let active = true;
    if (mode === "replacement") {
      getCorrectionDraft(invoice.id).then(draft => {
        if (!active) return;
        setExisting(draft); if (draft) setReason(draft.correction_reason || ""); setChecked(true);
      }).catch(e => {if (active) setError(getErrorMessage(e));});
    }
    if (mode === "delete") {
      getDeleteOptions(invoice.id).then(result => {
        if (active) {setEligibility(result.explanation); setChecked(true);}
      }).catch(e => {if (active) setError(getErrorMessage(e));});
    }
    if (mode === "history") {
      invoiceHistory(invoice.id).then(result => {if (active) setEvents(result);})
        .catch(e => {if (active) setError(getErrorMessage(e));});
    }
    return () => {active = false;};
  }, [invoice.id, mode]);
  async function run(fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(getErrorMessage(e)); }
    finally { lock.current = false; setBusy(false); }
  }
  function copy(replacement: boolean) {
    return run(async () => {
      const draft = replacement ? existing || await replacementInvoice(invoice.id, reason, key.current) : await duplicateInvoice(invoice.id, key.current);
      navigate(`/invoices/${draft.id}/edit`, {state: {correctionResumed: Boolean(existing || draft.correction_resumed)}}); onClose();
    });
  }
  const title = {delete: "Delete Invoice?", duplicate: "Duplicate Invoice", replacement: "Correct Issued Invoice", history: "Invoice History", archive: "Archive Invoice?"}[mode];
  return <Modal open onClose={() => {if (!busy) onClose();}} title={title} footer={<Button variant="secondary" disabled={busy} onClick={onClose}>Cancel / Close</Button>}>
    <ErrorBanner message={error}/>
    <p className="mb-2">Original Invoice: {invoice.invoice_number}</p>
    <p className="mb-4">Customer: {invoice.customer.name} | Status: {invoice.status.replaceAll("_", " ")}</p>
    {mode === "delete" && <form className="space-y-4" onSubmit={e => {e.preventDefault(); void run(async () => {const result = await deleteInvoice(invoice.id, invoice.version, reason); onDeleted(result.message); onClose();});}}><p>You are about to soft-delete invoice {invoice.invoice_number}. Audit evidence is retained. Are you sure you want to continue?</p><p>{eligibility}</p><label className="block">Deletion reason (optional)<textarea className="block border rounded-lg w-full p-2" maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label><Button type="submit" variant="danger" disabled={busy || !checked}>Delete Invoice</Button></form>}
    {mode === "archive" && <form className="space-y-4" onSubmit={e => {e.preventDefault(); void run(async () => {await archiveInvoice(invoice.id, invoice.version, reason); onDeleted("Invoice archived. Its financial status, contents and reserved number are unchanged."); onClose();});}}><p>Archive hides this invoice from the active list. It remains available in Archived invoices and keeps its number, financial contents and history. This does not cancel the invoice or issue a credit note. Its number cannot be reused.</p><label className="block">Archive reason<textarea className="block border rounded-lg w-full p-2" required maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label><Button type="submit" disabled={busy || !reason.trim()}>Archive Invoice</Button></form>}
    {mode === "duplicate" && <div className="space-y-4"><p>How would you like to duplicate this invoice?</p><p>Create a new draft invoice with a new unique invoice number.</p><Button disabled={busy} onClick={() => void copy(false)}>Create New Invoice</Button><Button variant="secondary" disabled={busy} onClick={() => setRevision(true)}>Create Revision of Existing Invoice</Button>{revision && <p role="status">Internal revisions are not supported by this system. {invoice.status === "draft" ? "Edit the existing draft to keep its number and recorded edit history, or create a new draft with a unique number." : "Use Create Correction / Replacement to create a linked draft with a unique number. The issued original remains unchanged."}</p>}</div>}
    {mode === "replacement" && <form className="space-y-4" onSubmit={e => {e.preventDefault(); void copy(true);}}><p>Invoice {invoice.invoice_number} has already been issued. To preserve financial records, create a correction or replacement rather than directly overwriting the issued invoice.</p><p role="status">{!checked ? "Checking for an existing correction draft..." : existing ? `Resume correction draft ${existing.invoice_number}. Your saved edits will be preserved.` : "A new linked correction draft will be created."}</p><p>The original remains unchanged. Before issuing this replacement, the original must be cancelled through an accounting-approved process. Credit notes and automatic cancellation are not supported.</p><label className="block">Correction reason<textarea className="block border rounded-lg w-full p-2" required readOnly={Boolean(existing)} maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label><Button type="submit" disabled={busy || !checked || (!existing && !reason.trim())}>{existing ? "Resume Correction Draft" : "Create Replacement Invoice"}</Button></form>}
    {mode === "history" && <><Button disabled={busy} onClick={() => void run(async () => setEvents(await invoiceHistory(invoice.id)))}>Load history</Button>{events?.length === 0 && <p>No recorded history is available.</p>}<ol className="space-y-4 mt-4">{events?.map((event, index) => <li key={index} className="border-l-2 border-primary pl-3"><p>{event.action.replaceAll("_", " ")}</p><p>{new Date(event.timestamp).toLocaleString("en-IN")} | User: {event.user_id || "Not recorded"}</p>{event.previous_status && <p>{event.previous_status} to {event.new_status}</p>}{event.related_invoice_number && <p>Related invoice: {event.related_invoice_number}</p>}{event.reason && <p>Reason: {event.reason}</p>}</li>)}</ol></>}
  </Modal>;
}

export function InvoiceReference({invoice}: {invoice: Invoice}) {
  return invoice.source_invoice_number ? <div className="border rounded-xl p-4 mb-4"><p>{invoice.replacement_for ? (invoice.status === "draft" ? "Correction draft for" : "Replacement for") : "Duplicated from"} {invoice.source_invoice_number}</p>{invoice.replacement_for && <p>Original status: {invoice.source_status || "See original invoice"}</p>}{invoice.correction_reason && <p>Correction reason: {invoice.correction_reason}</p>}</div> : null;
}
