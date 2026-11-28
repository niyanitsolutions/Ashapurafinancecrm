import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { apiRequest } from "@/shared/api/client";
import { todayISTDateString } from "@/shared/dateFormat";
import type { LoanCaseDetail } from "../api";

export function AdditionalDisbursementModal({ loanCase,onClose,onSaved }: {loanCase:LoanCaseDetail;onClose:()=>void;onSaved:()=>void}) {
  const [amount,setAmount]=useState("");const [date,setDate]=useState(todayISTDateString());const [reference,setReference]=useState("");const [remarks,setRemarks]=useState("");const [final,setFinal]=useState(true);const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);const [requestId]=useState(()=>crypto.randomUUID());
  const remaining=(loanCase.loan_details.offered_amount??0)-(loanCase.loan_details.disbursed_amount??0);
  return <Modal open onClose={onClose} title="Record additional disbursement" footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" form="additional-disbursement" loading={busy} disabled={!confirmed}>Confirm additional disbursement</Button></>}>
    <form id="additional-disbursement" className="space-y-3" onSubmit={e=>{e.preventDefault();setBusy(true);setError(null);void apiRequest(`/loan-cases/${loanCase.id}/disbursements`,{method:"POST",body:JSON.stringify({request_id:requestId,amount:Number(amount),disbursement_date:date,reference,remarks,final_disbursement:final})}).then(onSaved).catch(e=>setError(e.message)).finally(()=>setBusy(false));}}><ErrorBanner message={error}/>
      <p>Previously disbursed: ₹{loanCase.loan_details.disbursed_amount?.toLocaleString("en-IN")}. Remaining approved amount: ₹{remaining.toLocaleString("en-IN")}.</p>
      <FormField label="Additional disbursed amount" type="number" min="0.01" max={remaining} step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} required/>
      <FormField label="Additional disbursement date" type="date" value={date} onChange={e=>setDate(e.target.value)} required/>
      <FormField label="Additional payment reference" value={reference} onChange={e=>setReference(e.target.value)} required/>
      <FormField label="Additional disbursement remarks" value={remarks} onChange={e=>setRemarks(e.target.value)} required/>
      <label className="block"><input type="checkbox" checked={final} onChange={e=>setFinal(e.target.checked)}/>This is the final disbursement</label>
      <label className="block"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I confirm this additional disbursement has occurred and its payment reference is correct</label>
      <p className="text-xs text-textSecondary">The existing Loan Case, financial event and applicable commission commit together. This action records a confirmed payment.</p>
    </form>
  </Modal>;
}
