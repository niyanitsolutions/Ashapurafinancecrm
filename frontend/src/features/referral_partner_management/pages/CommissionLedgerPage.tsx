import { CommissionHistoryDialog } from "../components/CommissionHistoryDialog";
import { useEffect, useState } from "react";
import { apiRequest } from "@/shared/api/client";
import { todayISTDateString } from "@/shared/dateFormat";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { getErrorMessage } from "@/features/customer/errors";
import {
  approveCommissionEntry,
  listCommissionEntries,
  type CommissionEntry,
} from "@/features/referral_partner_management/api";

import { PartnerPayments } from "./PartnerPayments";

const PAGE_SIZE = 20;
function availableBalance(entry: CommissionEntry) {
  const outstanding=entry.outstanding_amount??entry.commission_amount+(entry.additional_earned_amount??0)+(entry.adjusted_amount??0)-(entry.paid_amount??0);
  return Math.max(0,Math.round((outstanding-(entry.reserved_amount??0))*100)/100);
}

function SettleModal({ entry, onClose, onSaved }: { entry: CommissionEntry; onClose: () => void; onSaved: () => void }) {
  const [paymentReference, setPaymentReference] = useState("");
  const [amount,setAmount]=useState(availableBalance(entry).toFixed(2));
  const [method,setMethod]=useState("bank_transfer");
  const [date,setDate]=useState(todayISTDateString());
  const [confirmed,setConfirmed]=useState(false);
  const [remarks,setRemarks]=useState("");
  const [requestId]=useState(()=>crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paymentReference.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await apiRequest(`/commission-entries/${entry.id}/payouts`,{method:"POST",body:JSON.stringify({request_id:requestId,amount:Number(amount),payment_reference:paymentReference.trim(),payment_method:method,payment_date:date,remarks,confirmed})});
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Record confirmed commission payment"
      description={`${entry.partner_name || entry.partner_id} · ₹${entry.commission_amount.toLocaleString()}`}
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="settle-commission-form" size="sm" loading={isSubmitting} disabled={!paymentReference.trim()||!confirmed}>
            Settle
          </Button>
        </>
      }
    >
      <form id="settle-commission-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <FormField label="Payment amount" type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} required/>
        <FormField label="Payment method" value={method} onChange={e=>setMethod(e.target.value)} required/>
        <FormField label="Payment date" type="date" value={date} onChange={e=>setDate(e.target.value)} required/>
        <FormField label="Internal payment remarks" value={remarks} onChange={e=>setRemarks(e.target.value)}/>
        <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I confirm this payment has been made and the reference is correct</label>
        <FormField label="Payment Reference" value={paymentReference} onChange={(e) => setPaymentReference(e.target.value)} required autoFocus />
      </form>
    </Modal>
  );
}

export function CommissionLedgerPage() {
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [reservationKey, setReservationKey] = useState(() => crypto.randomUUID());
  const [reserving, setReserving] = useState(false);
  const [decision, setDecision] = useState<{entry: CommissionEntry; action: "hold"|"resume"|"adjustment"}|null>(null);
  const [reason, setReason] = useState("");
  const [adjustment, setAdjustment] = useState("");
  const [adjustmentKey,setAdjustmentKey] = useState(() => crypto.randomUUID());
  const [historyId,setHistoryId]=useState<string|null>(null);
  const [items, setItems] = useState<CommissionEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [settleTarget, setSettleTarget] = useState<CommissionEntry | null>(null);

  const load = () => {
    setIsLoading(true);
    setSelected([]);
    listCommissionEntries({ page, page_size: PAGE_SIZE, status: status || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      load(); setRevision(value=>value+1);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="Commission Ledger"
      subtitle="Pending → Approved → Paid. Settlement is manual — there is no payment gateway integration yet; recording a reference here is the record of payment."
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="paid">Paid</option><option value="on_hold">On hold</option>
        </select>
        <Button disabled={!selected.length||reserving} loading={reserving} onClick={()=>{setReserving(true);void run(async()=>{await apiRequest("/partner-management/payments",{method:"POST",body:JSON.stringify({request_id:reservationKey,allocations:items.filter(e=>selected.includes(e.id)).map(e=>({entry_id:e.id,amount:availableBalance(e)}))})});setReservationKey(crypto.randomUUID());},"Payment reserved. Confirm after actual payment.").finally(()=>setReserving(false));}}>Reserve selected balances</Button>
      </div>

      {!isLoading && items.length === 0 ? (
        <EmptyState icon="commission" title="No commission entries yet" description="Entries appear here once a referred lead results in a disbursed loan or issued policy." />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Partner</th>
                <th className="px-4 py-3">Case</th>
                <th className="px-4 py-3">Base Amount</th>
                <th className="px-4 py-3">Commission</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
              {!isLoading &&
                items.map((entry) => (
                  <tr key={entry.id} className="border-b border-border last:border-0 hover:bg-background">
                    <td className="px-4 py-3">{entry.status==="approved"&&<input aria-label={`Select commission ${entry.id}`} type="checkbox" checked={selected.includes(entry.id)} disabled={availableBalance(entry)<=0} onChange={e=>setSelected(values=>e.target.checked?[...values,entry.id]:values.filter(id=>id!==entry.id))}/>} {entry.partner_name || entry.partner_id}</td>
                    <td className="px-4 py-3 capitalize">{entry.case_type}</td>
                    <td className="px-4 py-3">₹{entry.base_amount.toLocaleString()}</td>
                    <td className="px-4 py-3">₹{(entry.total_earned_amount??entry.commission_amount).toLocaleString()}<div className="text-xs">Approved: {entry.approved_amount??"Legacy approval"} - Paid: {entry.paid_amount??0} ? Outstanding: {entry.outstanding_amount??0} ? Reserved: {entry.reserved_amount??0}</div></td>
                    <td className="px-4 py-3 capitalize">{entry.status}</td>
                    <td className="px-4 py-3">
                      <Button size="sm" variant="secondary" onClick={()=>setHistoryId(entry.id)}>Earning history</Button>
                      {["pending","approved","on_hold"].includes(entry.status)&&<Button variant="secondary" size="sm" onClick={()=>{setReason("");setDecision({entry,action:entry.status==="on_hold"?"resume":"hold"});}}>{entry.status==="on_hold"?"Resume":"Hold"}</Button>}
                      <Button variant="secondary" size="sm" onClick={()=>{setReason("");setAdjustment("");setAdjustmentKey(crypto.randomUUID());setDecision({entry,action:"adjustment"});}}>Adjustment</Button>
                      {entry.status === "pending" && (
                        <button type="button" onClick={() => run(() => approveCommissionEntry(entry.id), "Commission entry approved.")} className="text-primary hover:underline text-xs">
                          Approve
                        </button>
                      )}
                      {entry.status === "approved" && (
                        <button type="button" disabled={availableBalance(entry)<=0} onClick={() => setSettleTarget(entry)} className="text-primary hover:underline text-xs">
                          Settle
                        </button>
                      )}
                      {entry.status === "paid" && entry.payment_reference && <span className="text-xs text-text/50">Ref: {entry.payment_reference}</span>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="entries" onPageChange={setPage} />

      {historyId&&<CommissionHistoryDialog entryId={historyId} onClose={()=>setHistoryId(null)}/>}
      <PartnerPayments revision={revision} onChanged={()=>{load();setRevision(value=>value+1);}}/>
      {decision&&<Modal open onClose={()=>setDecision(null)} title={decision.action==="adjustment"?"Record commission adjustment":"Review commission status"}><form className="space-y-4" onSubmit={e=>{e.preventDefault();void run(()=>apiRequest(`/commission-entries/${decision.entry.id}/${decision.action==="adjustment"?"adjustments":"decision"}`,{method:"POST",body:JSON.stringify(decision.action==="adjustment"?{request_id:adjustmentKey,amount:Number(adjustment),reason,kind:"adjustment"}:{version:decision.entry.version,reason,action:decision.action})}).then(()=>setDecision(null)),"Commission review recorded.");}}><ErrorBanner message={error}/>{decision.action==="adjustment"&&<FormField label="Signed adjustment amount" type="number" step="0.01" required value={adjustment} onChange={e=>setAdjustment(e.target.value)}/>}<FormField label="Reason" required minLength={3} value={reason} onChange={e=>setReason(e.target.value)}/><Button type="submit">Save review</Button></form></Modal>}
      {settleTarget && (
        <SettleModal
          entry={settleTarget}
          onClose={() => setSettleTarget(null)}
          onSaved={() => {
            setSettleTarget(null);
            setMessage("Commission entry settled.");
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
