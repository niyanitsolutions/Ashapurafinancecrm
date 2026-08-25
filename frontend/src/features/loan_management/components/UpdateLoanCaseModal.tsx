import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import {
  confirmOfferAcceptance,
  disburseLoanCase,
  moveLoanCaseBack,
  moveToCreditEvaluation,
  recordCreditEvaluation,
  recordEsignNachKyc,
  recordFinalEvaluation,
  recordRvOvRef,
  updateLoanCaseStatus,
  type BankOffer,
  type LoanCaseDetail,
} from "@/features/loan_management/api";
import { AdditionalDocumentsPanel } from "@/features/loan_management/components/AdditionalDocumentsPanel";
import { CreditEvaluationBankOffers } from "@/features/loan_management/components/CreditEvaluationBankOffers";
import { OfferAcceptancePanel } from "@/features/loan_management/components/OfferAcceptancePanel";
import { LOAN_STATUS_LABELS as STATUS_LABELS } from "@/features/loan_management/constants";
import { getLoanStatusControlInfo, type StatusControlAction } from "@/features/loan_management/statusControl";

// Decision #130: the ONE canonical stage-update flow. Opened from either the Loan
// Management list row (Update button) or the case detail page's own Update button —
// never the plain "View" page, which is read-only. Always renders the form matching the
// case's CURRENT stage (not whichever status the "Select Status" control might move it
// to next) — completing that form is what carries the case forward, exactly mirroring
// how the backend's dedicated actions already work (each one both saves stage data AND
// performs its own transition). A successful action that actually changed
// `current_status` closes the modal (matches the walkthrough: submit, confirm the status
// changed, click Update again for the next stage); one that only saved in-stage data
// (e.g. Credit Score, a bank/NBFC record) leaves it open so staff can keep working the
// same stage.
export function UpdateLoanCaseModal({
  caseId,
  loanCase,
  canEdit,
  canDisburse,
  onClose,
  onUpdated,
}: {
  caseId: string;
  loanCase: LoanCaseDetail;
  canEdit: boolean;
  canDisburse: boolean;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bankOffers, setBankOffers] = useState<BankOffer[]>(loanCase.bank_offers);
  const status = loanCase.current_status;
  const details = loanCase.loan_details;
  const selectedOffer = bankOffers.find((o) => o.is_selected) ?? null;

  const run = async (action: () => Promise<LoanCaseDetail>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      const updated = await action();
      onUpdated();
      if (updated.current_status !== status) {
        onClose();
      } else {
        setMessage(successMessage);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <Modal open title={`Update ${loanCase.case_code}`} description={`Current Status: ${STATUS_LABELS[status] ?? status}`} size="lg" onClose={onClose}>
      <div className="space-y-6">
        {message && <p className="text-sm text-success">{message}</p>}
        {error && <p className="text-sm text-danger">{error}</p>}

        {canEdit && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Select Status</h3>
            <StatusUpdateControl
              actions={getLoanStatusControlInfo(status, loanCase.allowed_next_statuses)}
              labels={STATUS_LABELS}
              onUpdate={(nextStatus, remarks) => run(() => updateLoanCaseStatus(caseId, nextStatus, remarks), "Status updated.")}
            />
          </div>
        )}

        {canEdit && loanCase.allowed_previous_statuses.length > 0 && (
          <MoveBackControl
            targetLabel={STATUS_LABELS[loanCase.allowed_previous_statuses[0]] ?? loanCase.allowed_previous_statuses[0]}
            onMoveBack={(remarks) => run(() => moveLoanCaseBack(caseId, remarks), "Case moved back.")}
          />
        )}

        {canEdit && status === "new_customer" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Bank / NBFC Offers</h3>
            <CreditEvaluationBankOffers caseId={caseId} canEdit={canEdit} stage="new_customer" onOffersChanged={setBankOffers} />
            <Button
              className="mt-3"
              size="sm"
              disabled={bankOffers.length === 0}
              onClick={() => run(() => moveToCreditEvaluation(caseId), "Moved to Credit Evaluation.")}
            >
              Move to Credit Evaluation
            </Button>
            {bankOffers.length === 0 && <p className="mt-1 text-xs text-text/40">Add at least one Bank / NBFC record first.</p>}
          </div>
        )}

        {canEdit && status === "credit_evaluation" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Bank / NBFC Offers</h3>
            <CreditEvaluationBankOffers
              caseId={caseId}
              canEdit={canEdit}
              stage="credit_evaluation"
              onOffersChanged={setBankOffers}
              onOfferSelected={() => {
                onUpdated();
                onClose();
              }}
            />
          </div>
        )}

        {canEdit && status === "credit_evaluation" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Credit Score (optional)</h3>
            <CreditScoreForm details={details} onSubmit={(payload) => run(() => recordCreditEvaluation(caseId, payload), "Credit score saved.")} />
          </div>
        )}

        {canEdit && status === "offer_acceptance" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Offer Acceptance</h3>
            <OfferAcceptancePanel
              bankName={loanCase.selected_bank_name}
              approvedAmount={loanCase.approved_amount}
              emiPerMonth={selectedOffer?.emi_per_month}
              canConfirm={canEdit}
              onConfirm={() => run(() => confirmOfferAcceptance(caseId), "Offer acceptance confirmed.")}
            />
          </div>
        )}

        {status === "additional_documents" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Additional Documents</h3>
            <AdditionalDocumentsPanel caseId={caseId} canEdit={canEdit} />
          </div>
        )}

        {canEdit && status === "rv_ov_ref" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">RV / OV / Ref</h3>
            <RvOvRefForm onSubmit={(payload) => run(() => recordRvOvRef(caseId, payload), "RV/OV/Ref recorded.")} />
          </div>
        )}

        {canEdit && status === "esign_nach_kyc" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">eSign / NACH / KYC Checklist</h3>
            <EsignNachKycForm details={details} onSubmit={(payload) => run(() => recordEsignNachKyc(caseId, payload), "eSign/NACH/KYC updated.")} />
          </div>
        )}

        {canEdit && status === "final_evaluation" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Decision Screen — Final Evaluation</h3>
            <DecisionForm
              onSubmit={(decision, reason, extra) =>
                run(() => recordFinalEvaluation(caseId, { remarks: extra.remarks, decision, rejection_reason: reason }), "Final evaluation recorded.")
              }
            />
          </div>
        )}

        {canDisburse && status === "send_for_disbursement" && (
          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Disbursement</h3>
            <DisburseForm onSubmit={(payload) => run(() => disburseLoanCase(caseId, payload), "Loan disbursed.")} />
          </div>
        )}
      </div>
    </Modal>
  );
}

// Renders the Case Status control's body based on what the current status actually
// allows (see statusControl.ts) — never a generic "pick anything" dropdown. A status can
// offer more than one action at once (decision #129 — e.g. Credit Evaluation's dedicated
// bank-offer view alongside plain Reject/Mark Re-Eligible moves). `onUpdate` is only ever
// called with one of the listed valid next statuses; the backend (WorkflowEngine +
// LoanCaseService.update_status) still independently validates and enforces every one of
// these rules regardless of what this component decides to show.
function StatusUpdateControl({
  actions,
  labels,
  onUpdate,
}: {
  actions: StatusControlAction[];
  labels: Record<string, string>;
  onUpdate: (nextStatus: string, remarks?: string) => void;
}) {
  // Decision #132: EVERY simple action requires this same explicit confirm step before
  // calling the backend — not just Reject. Clicking a row's button only reveals the
  // panel; nothing is called until "Confirm"/"Confirm Reject" is clicked, and "Cancel"
  // (or closing the modal) leaves the case completely untouched. This is what closes the
  // "one click, no data, instant transition" bug for every plain move, not only Reject.
  const [confirmingIndex, setConfirmingIndex] = useState<number | null>(null);
  const [confirmRemarks, setConfirmRemarks] = useState("");

  return (
    <div className="space-y-2">
      {actions.map((action, i) => {
        if (action.kind === "simple") {
          const isReject = action.nextStatus === "rejected";
          if (confirmingIndex === i) {
            return (
              <div key={i} className={`space-y-2 rounded border px-3 py-2 ${isReject ? "border-danger/30 bg-danger/5" : "border-border bg-background/50"}`}>
                <TextareaField
                  label={isReject ? "Reason (mandatory)" : "Remarks (optional)"}
                  value={confirmRemarks}
                  onChange={(e) => setConfirmRemarks(e.target.value)}
                  rows={2}
                  required={isReject}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={isReject ? "danger" : "primary"}
                    disabled={isReject && !confirmRemarks.trim()}
                    onClick={() => {
                      onUpdate(action.nextStatus, confirmRemarks.trim() || undefined);
                      setConfirmingIndex(null);
                      setConfirmRemarks("");
                    }}
                  >
                    {isReject ? "Confirm Reject" : "Confirm"}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setConfirmingIndex(null);
                      setConfirmRemarks("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            );
          }
          return (
            <div key={i} className="flex items-center justify-between gap-3 rounded border border-border bg-background/50 px-3 py-2">
              <span className="text-sm text-text/70">
                {action.label ? action.label : <>Next: <span className="font-medium text-text">{labels[action.nextStatus] ?? action.nextStatus}</span></>}
              </span>
              <Button size="sm" variant={isReject ? "danger" : "primary"} onClick={() => setConfirmingIndex(i)}>
                {isReject ? "Reject" : "Update Status"}
              </Button>
            </div>
          );
        }
        if (action.kind === "dedicated") {
          return (
            <p key={i} className="text-xs text-text/50">
              This status requires additional information. Please use the{" "}
              <span className="font-medium text-text">{action.actionLabel}</span> section below.
            </p>
          );
        }
        return (
          <p key={i} className="text-xs text-text/50">
            No direct status update is available from the current status.
          </p>
        );
      })}
    </div>
  );
}

// Generic "Move Back" (requirement 20) — the ONE configured previous status for the
// case's current status, read straight off the backend's own transition graph
// (`loanCase.allowed_previous_statuses`), not a client-side guess. Same explicit
// confirm-before-mutate pattern as every other action here.
function MoveBackControl({ targetLabel, onMoveBack }: { targetLabel: string; onMoveBack: (remarks?: string) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [remarks, setRemarks] = useState("");

  if (confirming) {
    return (
      <div className="space-y-2 rounded border border-border bg-background/50 px-3 py-2">
        <TextareaField label="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              onMoveBack(remarks.trim() || undefined);
              setConfirming(false);
              setRemarks("");
            }}
          >
            Confirm Move Back
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded border border-border bg-background/50 px-3 py-2">
      <span className="text-sm text-text/70">
        Move back to <span className="font-medium text-text">{targetLabel}</span>
      </span>
      <Button size="sm" variant="secondary" onClick={() => setConfirming(true)}>
        Move Back
      </Button>
    </div>
  );
}

function CreditScoreForm({ details, onSubmit }: { details: LoanCaseDetail["loan_details"]; onSubmit: (payload: { credit_score?: number; credit_remarks?: string }) => void }) {
  const [creditScore, setCreditScore] = useState(details.credit_score != null ? String(details.credit_score) : "");
  const [remarks, setRemarks] = useState(details.credit_remarks ?? "");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ credit_score: creditScore ? Number(creditScore) : undefined, credit_remarks: remarks || undefined });
      }}
      className="space-y-2"
    >
      <FormField label="Credit Score" type="number" value={creditScore} onChange={(e) => setCreditScore(e.target.value)} />
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <SubmitButton>Save</SubmitButton>
    </form>
  );
}

const RV_OV_REF_TYPES = [
  { value: "Residence Verification", label: "Residence Verification" },
  { value: "Office Verification", label: "Office Verification" },
  { value: "Reference Check", label: "Reference Check" },
];
const RV_OV_REF_RESULTS = [
  { value: "positive", label: "Positive" },
  { value: "negative", label: "Negative" },
  { value: "inconclusive", label: "Inconclusive" },
];

function RvOvRefForm({
  onSubmit,
}: {
  onSubmit: (payload: {
    rv_ov_ref_type: string; rv_ov_ref_status: string; rv_ov_ref_date: string;
    rv_ov_ref_verified_by: string; rv_ov_ref_result: string; rv_ov_ref_remarks?: string;
  }) => void;
}) {
  const [type, setType] = useState(RV_OV_REF_TYPES[0].value);
  const [status, setStatus] = useState("completed");
  const [date, setDate] = useState("");
  const [verifiedBy, setVerifiedBy] = useState("");
  const [result, setResult] = useState(RV_OV_REF_RESULTS[0].value);
  const [remarks, setRemarks] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          rv_ov_ref_type: type, rv_ov_ref_status: status, rv_ov_ref_date: new Date(date).toISOString(),
          rv_ov_ref_verified_by: verifiedBy, rv_ov_ref_result: result, rv_ov_ref_remarks: remarks || undefined,
        });
      }}
      className="space-y-2"
    >
      <SelectField label="Verification Type" name="rv_ov_ref_type" value={type} onChange={(e) => setType(e.target.value)} options={RV_OV_REF_TYPES} />
      <FormField label="Verification Status" name="rv_ov_ref_status" value={status} onChange={(e) => setStatus(e.target.value)} required />
      <FormField label="Verification Date" name="rv_ov_ref_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      <FormField label="Verified By" name="rv_ov_ref_verified_by" value={verifiedBy} onChange={(e) => setVerifiedBy(e.target.value)} required />
      <SelectField label="Verification Result" name="rv_ov_ref_result" value={result} onChange={(e) => setResult(e.target.value)} options={RV_OV_REF_RESULTS} />
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <SubmitButton disabled={!date || !verifiedBy}>Save &amp; Continue</SubmitButton>
    </form>
  );
}

function DecisionForm({
  onSubmit,
}: {
  onSubmit: (decision: "approved" | "rejected", rejectionReason: string | undefined, extra: { remarks?: string }) => void;
}) {
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [remarks, setRemarks] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [confirmReject, setConfirmReject] = useState(false);

  const submit = () => {
    onSubmit(decision, decision === "rejected" ? rejectionReason : undefined, { remarks: remarks || undefined });
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (decision === "rejected") {
          setConfirmReject(true);
          return;
        }
        submit();
      }}
      className="space-y-3"
    >
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <div className="flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" checked={decision === "approved"} onChange={() => setDecision("approved")} /> Approve
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /> Reject
        </label>
      </div>
      {decision === "rejected" && (
        <TextareaField label="Rejection reason (mandatory)" value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} rows={2} required />
      )}
      <SubmitButton>Submit Decision</SubmitButton>

      <ConfirmDialog
        open={confirmReject}
        title="Reject Case"
        message="Reject this case? This decision is recorded on the case history and cannot be undone here."
        confirmLabel="Reject Case"
        confirmVariant="danger"
        onConfirm={() => {
          submit();
          setConfirmReject(false);
        }}
        onClose={() => setConfirmReject(false)}
      />
    </form>
  );
}

function EsignNachKycForm({ details, onSubmit }: { details: LoanCaseDetail["loan_details"]; onSubmit: (payload: { esign_completed: boolean; nach_completed: boolean; kyc_completed: boolean }) => void }) {
  const [esign, setEsign] = useState(details.esign_completed);
  const [nach, setNach] = useState(details.nach_completed);
  const [kyc, setKyc] = useState(details.kyc_completed);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ esign_completed: esign, nach_completed: nach, kyc_completed: kyc });
      }}
      className="space-y-2"
    >
      <CheckboxField label="eSign completed" checked={esign} onChange={(e) => setEsign(e.target.checked)} />
      <CheckboxField label="NACH completed" checked={nach} onChange={(e) => setNach(e.target.checked)} />
      <CheckboxField label="KYC completed" checked={kyc} onChange={(e) => setKyc(e.target.checked)} />
      <SubmitButton>Save</SubmitButton>
    </form>
  );
}

function DisburseForm({ onSubmit }: { onSubmit: (payload: { disbursed_amount: number; disbursed_reference: string }) => void }) {
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setConfirmOpen(true);
      }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField label="Disbursed Amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        <FormField label="Reference / UTR" value={reference} onChange={(e) => setReference(e.target.value)} required />
      </div>
      <SubmitButton>Mark Disbursed</SubmitButton>

      <ConfirmDialog
        open={confirmOpen}
        title="Confirm Disbursement"
        message={`Mark this case as disbursed for ${amount ? `₹${amount}` : "the entered amount"} (ref: ${reference || "—"})? This cannot be undone here.`}
        confirmLabel="Confirm Disbursement"
        onConfirm={() => {
          onSubmit({ disbursed_amount: Number(amount), disbursed_reference: reference });
          setConfirmOpen(false);
        }}
        onClose={() => setConfirmOpen(false)}
      />
    </form>
  );
}
