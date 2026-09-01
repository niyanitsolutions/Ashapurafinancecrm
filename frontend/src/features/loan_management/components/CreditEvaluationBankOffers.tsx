import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addBankOffer,
  deleteBankOffer,
  listBankOffers,
  selectBankOffer,
  updateBankOffer,
  type BankOffer,
  type BankOfferPayload,
} from "@/features/loan_management/api";

const DECISION_LABELS: Record<string, string> = { pending: "Pending", approved: "Approved", rejected_re_eligible: "Rejected / Re-Eligible" };

// Bank/NBFC Offers panel — used at BOTH New Customer (bank/branch/loan-type/amount
// capture only, no decision yet) and Credit Evaluation (the SAME record edited in place
// to add its decision) — decision #129/this round's redesign: a case can carry any
// number of these; adding one never overwrites another, and staff is never asked to
// re-enter data already captured at New Customer. Selecting an offer (Credit Evaluation
// only) is a SEPARATE step from confirming acceptance (see OfferAcceptancePanel).
export function CreditEvaluationBankOffers({
  caseId,
  canEdit,
  stage,
  onOfferSelected,
  onOffersChanged,
}: {
  caseId: string;
  canEdit: boolean;
  stage: "new_customer" | "credit_evaluation";
  onOfferSelected?: () => void;
  onOffersChanged?: (offers: BankOffer[]) => void;
}) {
  const [offers, setOffers] = useState<BankOffer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingOffer, setEditingOffer] = useState<BankOffer | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [confirmSelectId, setConfirmSelectId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const load = () => {
    listBankOffers(caseId)
      .then((result) => {
        setOffers(result);
        onOffersChanged?.(result);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  // Deliberately keyed only on caseId — `onOffersChanged` is a fresh inline closure on
  // every parent render; including it would reload the list every render instead of only
  // when the case actually changes (same established pattern as this file's siblings,
  // e.g. LoanCaseDetailsPage's own `useEffect(load, [caseId])`).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [caseId]);

  const handleAdd = async (payload: BankOfferPayload) => {
    setError(null);
    try {
      await addBankOffer(caseId, payload);
      setShowAddForm(false);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleEdit = async (payload: BankOfferPayload) => {
    if (!editingOffer) return;
    setError(null);
    try {
      await updateBankOffer(caseId, editingOffer.id, payload);
      setEditingOffer(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleDelete = async (offerId: string) => {
    setError(null);
    try {
      await deleteBankOffer(caseId, offerId);
      setConfirmDeleteId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleSelect = async (offerId: string) => {
    setError(null);
    try {
      await selectBankOffer(caseId, offerId);
      setConfirmSelectId(null);
      onOfferSelected?.();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  // Production fix — the case's forward move to Offer Acceptance already exists (see
  // `handleSelect`/`selectBankOffer`, decision #129): it's reached by approving a bank
  // offer's decision (Edit Bank -> Bank Decision: Approved -> Save) and then clicking
  // Select, never a bare status-only button — the amount/rate/tenure/EMI recorded there
  // is required data Offer Acceptance's own screen depends on. That mechanism was never
  // broken, just not obviously connected to "how do I move this case forward" — this
  // note makes the connection explicit right where staff are already looking, instead of
  // adding a second, bypass-the-data way to reach the same status.
  const hasSelectableOrSelectedOffer = offers.some((o) => o.is_selected || o.decision === "approved");
  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-danger">{error}</p>}

      {stage === "credit_evaluation" && !hasSelectableOrSelectedOffer && (
        <p className="text-sm text-text/60">
          To move this case to <span className="font-medium text-text">Offer Acceptance</span>, edit a bank/NBFC offer below, set its Bank Decision to
          "Approved" with the approved amount and EMI, save it, then click <span className="font-medium text-text">Select</span>.
        </p>
      )}

      {offers.length === 0 && <p className="text-sm text-text/40">No bank/NBFC offers recorded yet.</p>}

      {offers.map((offer) =>
        editingOffer?.id === offer.id ? (
          <BankOfferForm key={offer.id} stage={stage} initial={offer} onSubmit={handleEdit} onCancel={() => setEditingOffer(null)} />
        ) : (
          <div key={offer.id} className="rounded border border-border p-3 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-medium text-text">{offer.bank_name}</span>
              {offer.is_selected && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-semibold text-primary">Selected</span>}
            </div>
            {(offer.branch || offer.loan_type || offer.requested_amount != null) && (
              <div className="text-xs text-text/50">
                {offer.branch && <span>Branch: {offer.branch} </span>}
                {offer.loan_type && <span>Loan Type: {offer.loan_type} </span>}
                {offer.requested_amount != null && <span>Requested Amount: ₹{offer.requested_amount.toLocaleString("en-IN")}</span>}
              </div>
            )}
            {offer.remarks && <div className="text-xs text-text/50">Remarks: {offer.remarks}</div>}
            {stage === "credit_evaluation" && (
              <div className="text-sm text-text/70">
                Bank Decision: {DECISION_LABELS[offer.decision] ?? offer.decision}
                {offer.decision === "approved" && offer.approved_amount != null && (
                  <span> — Approved Amount: ₹{offer.approved_amount.toLocaleString("en-IN")}</span>
                )}
              </div>
            )}
            {stage === "credit_evaluation" && offer.decision === "approved" && (
              <div className="text-xs text-text/50">
                {offer.interest_rate != null && <span>Interest Rate: {offer.interest_rate}% </span>}
                {offer.tenure_months != null && <span>Tenure: {offer.tenure_months} months </span>}
                {offer.processing_fee != null && <span>Processing Fee: ₹{offer.processing_fee.toLocaleString("en-IN")} </span>}
                {offer.emi_per_month != null && <span>EMI Per Month: ₹{offer.emi_per_month.toLocaleString("en-IN")}</span>}
              </div>
            )}
            {canEdit && (
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="secondary" onClick={() => setEditingOffer(offer)}>
                  {stage === "new_customer" ? "Edit" : "Edit Bank"}
                </Button>
                {!offer.is_selected && (
                  <Button size="sm" variant="secondary" onClick={() => setConfirmDeleteId(offer.id)}>
                    Delete
                  </Button>
                )}
                {stage === "credit_evaluation" && offer.decision === "approved" && !offer.is_selected && (
                  <Button size="sm" onClick={() => setConfirmSelectId(offer.id)}>
                    Select
                  </Button>
                )}
              </div>
            )}
          </div>
        )
      )}

      {canEdit && !showAddForm && (
        <Button size="sm" variant="secondary" onClick={() => setShowAddForm(true)}>
          + Add Other Bank
        </Button>
      )}
      {canEdit && showAddForm && <BankOfferForm stage={stage} onSubmit={handleAdd} onCancel={() => setShowAddForm(false)} />}

      <ConfirmDialog
        open={confirmSelectId !== null}
        title="Select This Offer"
        message="Select this bank offer as the case's final offer? The case will move to Offer Acceptance. This does not yet confirm acceptance — a separate confirmation step is still required."
        confirmLabel="Select Offer"
        onConfirm={() => {
          if (confirmSelectId) return handleSelect(confirmSelectId);
        }}
        onClose={() => setConfirmSelectId(null)}
      />

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Delete Bank / NBFC Record"
        message="Remove this bank/NBFC record from the case? This cannot be undone."
        confirmLabel="Delete"
        confirmVariant="danger"
        onConfirm={() => {
          if (confirmDeleteId) return handleDelete(confirmDeleteId);
        }}
        onClose={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}

function BankOfferForm({
  stage,
  initial,
  onSubmit,
  onCancel,
}: {
  stage: "new_customer" | "credit_evaluation";
  initial?: BankOffer;
  onSubmit: (payload: BankOfferPayload) => void;
  onCancel: () => void;
}) {
  const [bankName, setBankName] = useState(initial?.bank_name ?? "");
  const [branch, setBranch] = useState(initial?.branch ?? "");
  const [loanType, setLoanType] = useState(initial?.loan_type ?? "");
  const [requestedAmount, setRequestedAmount] = useState(initial?.requested_amount != null ? String(initial.requested_amount) : "");
  const [bankApplicationId, setBankApplicationId] = useState(initial?.bank_application_id ?? "");
  const [referenceNumber, setReferenceNumber] = useState(initial?.reference_number ?? "");
  const [assignedOfficer, setAssignedOfficer] = useState(initial?.assigned_officer ?? "");
  const [decision, setDecision] = useState<"pending" | "approved" | "rejected_re_eligible">(
    (initial?.decision as "pending" | "approved" | "rejected_re_eligible") ?? "pending",
  );
  const [approvedAmount, setApprovedAmount] = useState(initial?.approved_amount != null ? String(initial.approved_amount) : "");
  const [interestRate, setInterestRate] = useState(initial?.interest_rate != null ? String(initial.interest_rate) : "");
  const [tenureMonths, setTenureMonths] = useState(initial?.tenure_months != null ? String(initial.tenure_months) : "");
  const [processingFee, setProcessingFee] = useState(initial?.processing_fee != null ? String(initial.processing_fee) : "");
  const [emiPerMonth, setEmiPerMonth] = useState(initial?.emi_per_month != null ? String(initial.emi_per_month) : "");
  const [remarks, setRemarks] = useState(initial?.remarks ?? "");

  const showDecisionFields = stage === "credit_evaluation";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          bank_name: bankName,
          branch: branch || undefined,
          loan_type: loanType || undefined,
          requested_amount: requestedAmount ? Number(requestedAmount) : undefined,
          bank_application_id: bankApplicationId || undefined,
          reference_number: referenceNumber || undefined,
          assigned_officer: assignedOfficer || undefined,
          decision: showDecisionFields ? decision : "pending",
          approved_amount: showDecisionFields && decision === "approved" ? Number(approvedAmount) : undefined,
          interest_rate: showDecisionFields && decision === "approved" && interestRate ? Number(interestRate) : undefined,
          tenure_months: showDecisionFields && decision === "approved" && tenureMonths ? Number(tenureMonths) : undefined,
          processing_fee: showDecisionFields && decision === "approved" && processingFee ? Number(processingFee) : undefined,
          emi_per_month: showDecisionFields && decision === "approved" ? Number(emiPerMonth) : undefined,
          remarks: remarks || undefined,
        });
      }}
      className="rounded border border-border p-3 space-y-2"
    >
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <FormField label="Bank / NBFC Name" name="bank_name" value={bankName} onChange={(e) => setBankName(e.target.value)} required />
        <FormField label="Branch" name="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
        <FormField label="Loan Type" name="loan_type" value={loanType} onChange={(e) => setLoanType(e.target.value)} />
        <FormField label="Requested Amount" name="requested_amount" type="number" value={requestedAmount} onChange={(e) => setRequestedAmount(e.target.value)} />
      </div>
      {showDecisionFields && (
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Bank Application ID" name="bank_application_id" value={bankApplicationId} onChange={(e) => setBankApplicationId(e.target.value)} />
          <FormField label="Reference Number" name="reference_number" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} />
          <FormField label="Assigned Officer" name="assigned_officer" value={assignedOfficer} onChange={(e) => setAssignedOfficer(e.target.value)} />
        </div>
      )}
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      {showDecisionFields && (
        <>
          <SelectField
            label="Bank Decision"
            value={decision}
            onChange={(e) => setDecision(e.target.value as "pending" | "approved" | "rejected_re_eligible")}
            options={[
              { value: "pending", label: "Pending" },
              { value: "approved", label: "Approved" },
              { value: "rejected_re_eligible", label: "Rejected / Re-Eligible" },
            ]}
          />
          {decision === "approved" && (
            <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
              <FormField label="Approved Amount" name="approved_amount" type="number" value={approvedAmount} onChange={(e) => setApprovedAmount(e.target.value)} required />
              <FormField label="Interest Rate (%)" name="interest_rate" type="number" value={interestRate} onChange={(e) => setInterestRate(e.target.value)} />
              <FormField label="Tenure (months)" name="tenure_months" type="number" value={tenureMonths} onChange={(e) => setTenureMonths(e.target.value)} />
              <FormField label="Processing Fee" name="processing_fee" type="number" value={processingFee} onChange={(e) => setProcessingFee(e.target.value)} />
              <FormField label="EMI Per Month" name="emi_per_month" type="number" value={emiPerMonth} onChange={(e) => setEmiPerMonth(e.target.value)} required />
            </div>
          )}
        </>
      )}
      <div className="flex gap-2">
        <SubmitButton>Save Bank</SubmitButton>
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
