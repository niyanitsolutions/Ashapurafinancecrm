import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { getErrorMessage } from "@/shared/api/errors";
import { deleteInvoice, duplicateInvoice, invoiceHistory, replacementInvoice, type Invoice, type InvoiceEvent } from "./api";

export type Workflow = "delete" | "duplicate" | "replacement" | "history";
export function InvoiceWorkflow({invoice, mode, onClose, onDeleted}: {
  invoice: Invoice; mode: Workflow; onClose: () => void; onDeleted: () => void;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [events, setEvents] = useState<InvoiceEvent[] | null>(null);
  const [revision, setRevision] = useState(false);
  const key = useRef(crypto.randomUUID());
  async function run(fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(getErrorMessage(e)); }
    finally { lock.current = false; setBusy(false); }
  }
  function copy(replacement: boolean) {
    return run(async () => {
      const draft = replacement ? await replacementInvoice(invoice.id, reason, key.current) : await duplicateInvoice(invoice.id, key.current);
      navigate(`/invoices/${draft.id}/edit`); onClose();
    });
  }
  const title = {delete: "Delete Invoice?", duplicate: "Duplicate Invoice", replacement: "Correct Issued Invoice", history: "Invoice History"}[mode];
  return <Modal open onClose={() => {if (!busy) onClose();}} title={title} footer={<Button variant="secondary" disabled={busy} onClick={onClose}>Cancel / Close</Button>}>
    <ErrorBanner message={error}/>
    <p className="mb-4">Original Invoice: {invoice.invoice_number}</p>
    {mode === "delete" && <><p>You are about to delete invoice {invoice.invoice_number}. This action may not be reversible. Are you sure you want to continue?</p><Button variant="danger" disabled={busy} onClick={() => void run(async () => {await deleteInvoice(invoice.id, invoice.version); onDeleted(); onClose();})}>Delete Invoice</Button></>}
    {mode === "duplicate" && <div className="space-y-4"><p>How would you like to duplicate this invoice?</p><p>Create a new draft invoice with a new unique invoice number.</p><Button disabled={busy} onClick={() => void copy(false)}>Create New Invoice</Button><Button variant="secondary" disabled={busy} onClick={() => setRevision(true)}>Create Revision of Existing Invoice</Button>{revision && <p role="status">Internal revisions are not supported by this system. {invoice.status === "draft" ? "Edit the existing draft to keep its number and recorded edit history, or create a new draft with a unique number." : "Use Create Correction / Replacement to create a linked draft with a unique number. The issued original remains unchanged."}</p>}</div>}
    {mode === "replacement" && <form className="space-y-4" onSubmit={e => {e.preventDefault(); void copy(true);}}><p>Invoice {invoice.invoice_number} has already been issued. To preserve financial records, create a correction or replacement rather than directly overwriting the issued invoice.</p><p>The original remains unchanged. Before issuing this replacement, the original must be cancelled through an accounting-approved process. Credit notes and automatic cancellation are not supported.</p><label className="block">Correction reason<textarea className="block border rounded-lg w-full p-2" required maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/></label><Button type="submit" disabled={busy || !reason.trim()}>Create Replacement Invoice</Button></form>}
    {mode === "history" && <><Button disabled={busy} onClick={() => void run(async () => setEvents(await invoiceHistory(invoice.id)))}>Load history</Button>{events?.length === 0 && <p>No recorded history is available.</p>}<ol className="space-y-4 mt-4">{events?.map((event, index) => <li key={index} className="border-l-2 border-primary pl-3"><p>{event.action.replaceAll("_", " ")}</p><p>{new Date(event.timestamp).toLocaleString("en-IN")} ? User: {event.user_id || "Not recorded"}</p>{event.previous_status && <p>{event.previous_status} ? {event.new_status}</p>}{event.related_invoice_number && <p>Related invoice: {event.related_invoice_number}</p>}{event.reason && <p>Reason: {event.reason}</p>}</li>)}</ol></>}
  </Modal>;
}

export function InvoiceReference({invoice}: {invoice: Invoice}) {
  return invoice.source_invoice_number ? <div className="border rounded-xl p-4 mb-4"><p>{invoice.replacement_for ? "Replacement for" : "Duplicated from"} {invoice.source_invoice_number}</p>{invoice.correction_reason && <p>Correction reason: {invoice.correction_reason}</p>}</div> : null;
}
