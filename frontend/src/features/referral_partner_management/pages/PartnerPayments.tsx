import { useEffect, useState } from "react";
import { apiRequest, apiRequestRaw } from "@/shared/api/client";
import { todayISTDateString } from "@/shared/dateFormat";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";

type Payment = { id: string; partner_id: string; amount: number; status: string; entry_id?:string; payment_reference?:string; payment_date?:string; payment_method?:string; remarks?:string; allocations?: { entry_id: string; amount: number }[] };
type Exception = { id: string; reason: string; case_id: string; eligible_base_amount: number; status: string };

export function PartnerPayments({ revision, onChanged }: { revision: number; onChanged: () => void }) {
  const [status,setStatus]=useState("initiated");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [exceptionPage, setExceptionPage] = useState(1);
  const [exceptionTotal, setExceptionTotal] = useState(0);
  const [target, setTarget] = useState<{ id: string; action: "confirm" | "cancel" | "resolve" } | null>(null);
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [method, setMethod] = useState("bank_transfer");
  const [date, setDate] = useState(todayISTDateString());
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    void Promise.all([
      apiRequestRaw<Payment[]>(`/partner-management/payments?page=${page}&page_size=20&status=${status}`),
      apiRequestRaw<Exception[]>(`/partner-management/commission-exceptions?page=${exceptionPage}&page_size=20`),
    ]).then(([p, e]) => {
      if (!current) return;
      setPayments(p.data ?? []); setTotal(p.meta?.pagination?.total ?? 0);
      setExceptions(e.data ?? []); setExceptionTotal(e.meta?.pagination?.total ?? 0);
    }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [revision, page, exceptionPage,status]);
  const open = (id: string, action: "confirm" | "cancel" | "resolve") => {
    setReason(""); setReference(""); setConfirmed(false); setError(null); setTarget({ id, action });
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!target || busy) return;
    setBusy(true); setError(null);
    try {
      const path = target.action === "resolve" ? `/partner-management/commission-exceptions/${target.id}/resolve` : `/partner-management/payments/${target.id}/${target.action}`;
      await apiRequest(path, { method: "POST", body: JSON.stringify(target.action === "confirm" ? { payment_reference: reference, payment_method: method, payment_date: date, confirmed } : { reason }) });
      setTarget(null); onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : "Action failed."); }
    finally { setBusy(false); }
  };
  return <section className="mt-6 space-y-4">
    <ErrorBanner message={error} />
    <h2 className="text-xl font-semibold">Payments and reservations</h2><label>Payment status<select className="ml-2 rounded border border-border bg-card p-2" value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}><option value="initiated">Initiated reservations</option><option value="confirmed">Confirmed payments</option><option value="cancelled">Cancelled reservations</option><option value="">All payments</option></select></label>
    <p className="text-sm text-textSecondary">Reservations protect available balances. Confirm only after making the payment outside CRM.</p>
    {payments.map(p => <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border p-3" key={p.id}><span>Partner {p.partner_id} · ₹{p.amount.toLocaleString("en-IN")} · {p.allocations?.length??1} commissions - {p.status} {p.payment_reference?`- ${p.payment_reference} - ${p.payment_date} - ${p.payment_method}`:""}</span>{p.status==="initiated"&&<><Button onClick={() => open(p.id, "confirm")}>Confirm actual payment</Button><Button variant="secondary" onClick={() => open(p.id, "cancel")}>Cancel reservation</Button></>}{p.remarks&&<p className="text-sm">{p.remarks}</p>}</div>)}
    {!payments.length && <p>No matching payments.</p>}
    <div className="flex gap-3"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous payments</Button><span>Page {page}</span><Button disabled={page * 20 >= total} onClick={() => setPage(page + 1)}>Next payments</Button></div>
    <h2 className="text-xl font-semibold">Commission exceptions</h2>
    <p className="text-sm text-textSecondary">Correct the applicable rule or attribution, then resolve against the original confirmed financial event.</p>
    {exceptions.map(item => <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border p-3"><span>Case {item.case_id} · {item.reason.replaceAll("_", " ")} · eligible base ₹{item.eligible_base_amount.toLocaleString("en-IN")}</span><Button onClick={() => open(item.id, "resolve")}>Resolve exception</Button></div>)}
    {!exceptions.length && <p>No open exceptions.</p>}
    <div className="flex gap-3"><Button disabled={exceptionPage === 1} onClick={() => setExceptionPage(exceptionPage - 1)}>Previous exceptions</Button><span>Page {exceptionPage}</span><Button disabled={exceptionPage * 20 >= exceptionTotal} onClick={() => setExceptionPage(exceptionPage + 1)}>Next exceptions</Button></div>
    {target && <Modal open onClose={() => !busy && setTarget(null)} title={target.action === "confirm" ? "Confirm actual payment" : target.action === "cancel" ? "Cancel payment reservation" : "Resolve commission exception"}>
      <form onSubmit={submit} className="space-y-4"><ErrorBanner message={error} />
        {target.action === "confirm" ? <><FormField label="Payment reference" required value={reference} onChange={e => setReference(e.target.value)} /><FormField label="Payment method" required value={method} onChange={e => setMethod(e.target.value)} /><FormField label="Payment date" type="date" required value={date} onChange={e => setDate(e.target.value)} /><label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I confirm this payment was made and the reference is correct</label></> : <FormField label="Reason" required minLength={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />}
        <Button type="submit" loading={busy} disabled={target.action === "confirm" && !confirmed}>Save</Button>
      </form>
    </Modal>}
  </section>;
}
