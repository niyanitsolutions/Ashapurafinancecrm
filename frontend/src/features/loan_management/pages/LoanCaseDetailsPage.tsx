import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addLoanCaseNote,
  assignLoanCase,
  disburseLoanCase,
  getLoanCase,
  getLoanCaseTimeline,
  holdLoanCase,
  recordBankDetails,
  recordCreditEvaluation,
  recordEsignNachKyc,
  recordFinalEvaluation,
  recordOffer,
  requestLoanCaseDocuments,
  resumeLoanCase,
  verifyLoanCaseDocuments,
  type CaseTimelineEntry,
  type LoanCaseDetail,
} from "@/features/loan_management/api";
import { documentTypesApi, type NamedMasterData } from "@/features/system_settings/api";
import { HOLD_REASONS } from "@/features/workflow_engine/holdReasons";

const STATUS_LABELS: Record<string, string> = {
  new_customer: "New Customer",
  documents_pending: "Documents Pending",
  credit_evaluation: "Credit Evaluation",
  offer_acceptance: "Offer Acceptance",
  additional_documents: "Upload Additional Documents",
  esign_nach_kyc: "eSign / NACH / KYC",
  final_evaluation: "Final Evaluation",
  send_for_disbursement: "Send For Disbursement",
  disbursed: "Disbursed",
  on_hold: "On Hold",
  rejected: "Rejected",
};

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm">{value ?? "—"}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3">
      <h3 className="text-sm font-semibold text-text/70">{title}</h3>
      {children}
    </div>
  );
}

export function LoanCaseDetailsPage() {
  const { can } = usePermissions();
  // loan_management:applications's real backend actions: view/edit/approve/reject/
  // assign — no "create" (cases originate from the workflow engine). "edit" covers
  // every write below except Assign (assign) and Disburse (approve), which are
  // separately, more coarsely permissioned server-side.
  const canEdit = can("loan_management:applications", "edit");
  const canAssign = can("loan_management:applications", "assign");
  const canDisburse = can("loan_management:applications", "approve");
  const { caseId } = useParams<{ caseId: string }>();
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [documentTypes, setDocumentTypes] = useState<NamedMasterData[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmVerify, setConfirmVerify] = useState(false);

  const load = () => {
    if (!caseId) return;
    getLoanCase(caseId).then(setLoanCase).catch((err) => setError(getErrorMessage(err)));
    getLoanCaseTimeline(caseId).then(setTimeline).catch(() => setTimeline([]));
  };

  useEffect(load, [caseId]);
  useEffect(() => {
    documentTypesApi.list().then(setDocumentTypes).catch(() => setDocumentTypes([]));
  }, []);

  if (!caseId) return null;

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  if (error && !loanCase) {
    return (
      <SimplePageLayout title="Loan Case" backTo="/loan-cases">
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!loanCase) {
    return (
      <SimplePageLayout title="Loan Case" backTo="/loan-cases">
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  const status = loanCase.current_status;
  const details = loanCase.loan_details;

  return (
    <SimplePageLayout title={`${loanCase.case_code} — ${STATUS_LABELS[status] ?? status}`} backTo="/loan-cases">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      {loanCase.rejection_reason && (
        <div className="mb-4 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          Rejected — {loanCase.rejection_reason}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Section title="Case Overview">
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              <Field label="Customer" value={loanCase.customer_name} />
              <Field label="Product" value={loanCase.product_name} />
              <Field label="Assigned To" value={loanCase.assigned_to_name} />
              <Field label="Status" value={STATUS_LABELS[status] ?? status} />
            </div>
          </Section>

          {canEdit && (
            <Section title="Bank / NBFC Details">
              <BankDetailsForm
                details={details}
                onSubmit={(payload) => run(() => recordBankDetails(caseId, payload), "Bank details updated.")}
              />
            </Section>
          )}

          {canEdit && (status === "new_customer" || status === "documents_pending" || status === "additional_documents") && (
            <Section title="Document Verification">
              <p className="text-xs text-text/50">Pending: {loanCase.pending_document_type_ids.length === 0 ? "none requested" : loanCase.pending_document_type_ids.length}</p>
              <RequestDocumentsForm
                documentTypes={documentTypes}
                onSubmit={(ids) => run(() => requestLoanCaseDocuments(caseId, ids), "Documents requested.")}
              />
              {status !== "new_customer" && (
                <Button size="sm" onClick={() => setConfirmVerify(true)}>
                  Verify Documents
                </Button>
              )}
            </Section>
          )}

          {canEdit && status === "credit_evaluation" && (
            <Section title="Decision Screen — Credit Evaluation">
              <DecisionForm
                onSubmit={(decision, reason, extra) =>
                  run(() => recordCreditEvaluation(caseId, { credit_score: extra.creditScore, credit_remarks: extra.remarks, decision, rejection_reason: reason }), "Credit evaluation recorded.")
                }
                extraFields="credit"
              />
            </Section>
          )}

          {status === "offer_acceptance" && (
            <Section title="Loan Offer">
              {details.offered_amount == null ? (
                canEdit ? (
                  <OfferForm onSubmit={(payload) => run(() => recordOffer(caseId, payload), "Offer issued.")} />
                ) : (
                  <p className="text-sm text-text/40">No offer recorded yet.</p>
                )
              ) : (
                <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                  <Field label="Offered Amount" value={details.offered_amount} />
                  <Field label="Tenure (months)" value={details.offered_tenure_months} />
                  <Field label="Interest Rate" value={details.offered_interest_rate} />
                  <Field label="Customer Decision" value={details.offer_decision} />
                </div>
              )}
              <p className="text-xs text-text/40">Awaiting the Customer's own accept/decline action.</p>
            </Section>
          )}

          {canEdit && status === "esign_nach_kyc" && (
            <Section title="eSign / NACH / KYC Checklist">
              <EsignNachKycForm
                details={details}
                onSubmit={(payload) => run(() => recordEsignNachKyc(caseId, payload), "eSign/NACH/KYC updated.")}
              />
            </Section>
          )}

          {canEdit && status === "final_evaluation" && (
            <Section title="Decision Screen — Final Evaluation">
              <DecisionForm
                onSubmit={(decision, reason, extra) => run(() => recordFinalEvaluation(caseId, { remarks: extra.remarks, decision, rejection_reason: reason }), "Final evaluation recorded.")}
                extraFields="remarks"
              />
            </Section>
          )}

          {canDisburse && status === "send_for_disbursement" && (
            <Section title="Disbursement">
              <DisburseForm onSubmit={(payload) => run(() => disburseLoanCase(caseId, payload), "Loan disbursed.")} />
            </Section>
          )}

          {status === "disbursed" && (
            <Section title="Disbursement Record">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Disbursed Amount" value={details.disbursed_amount} />
                <Field label="Reference" value={details.disbursed_reference} />
                <Field label="Disbursed At" value={details.disbursed_at ? new Date(details.disbursed_at).toLocaleString() : null} />
              </div>
            </Section>
          )}
        </div>

        <div className="space-y-6">
          {canAssign && (
            <Section title="Assignment">
              <AssignForm
                currentName={loanCase.assigned_to_name}
                onSubmit={(employeeId) => run(() => assignLoanCase(caseId, employeeId), "Case assigned.")}
              />
            </Section>
          )}

          {canEdit && status !== "disbursed" && status !== "rejected" && (
            <Section title="Case Status Control">
              {status === "on_hold" ? (
                <Button size="sm" className="w-full" onClick={() => run(() => resumeLoanCase(caseId), "Case resumed.")}>
                  Resume
                </Button>
              ) : (
                <HoldForm onSubmit={(reason, remarks) => run(() => holdLoanCase(caseId, reason, remarks), "Case placed on hold.")} />
              )}
            </Section>
          )}

          <Section title="Application History">
            {canEdit && <NoteForm onSubmit={(text) => run(() => addLoanCaseNote(caseId, text), "Note added.")} />}
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {timeline.length === 0 && <p className="text-sm text-text/40">No activity yet.</p>}
              {timeline.map((entry, i) => (
                <div key={i} className="border-l-2 border-border pl-3 py-1">
                  {entry.type === "note" ? (
                    <div className="text-sm text-text">{entry.text}</div>
                  ) : (
                    <div className="text-sm text-text/70">
                      {entry.from_status ? `${STATUS_LABELS[entry.from_status] ?? entry.from_status} → ` : ""}
                      {STATUS_LABELS[entry.to_status ?? ""] ?? entry.to_status}
                      {entry.remarks ? ` (${entry.remarks})` : ""}
                    </div>
                  )}
                  <div className="text-xs text-text/40">{new Date(entry.created_at).toLocaleString()}</div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>

      <ConfirmDialog
        open={confirmVerify}
        title="Verify Documents"
        message="Mark all requested documents as verified for this case? This moves the case to the next stage."
        confirmLabel="Verify Documents"
        onConfirm={async () => {
          await run(() => verifyLoanCaseDocuments(caseId), "Documents verified.");
          setConfirmVerify(false);
        }}
        onClose={() => setConfirmVerify(false)}
      />
    </SimplePageLayout>
  );
}

function AssignForm({ currentName, onSubmit }: { currentName: string | null; onSubmit: (employeeId: string) => void }) {
  const [employeeId, setEmployeeId] = useState("");
  return (
    <div className="space-y-2">
      {currentName && <p className="text-sm text-text/70">Currently: {currentName}</p>}
      <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} />
      <Button size="sm" className="w-full" disabled={!employeeId} onClick={() => onSubmit(employeeId)}>
        {currentName ? "Reassign" : "Assign"}
      </Button>
    </div>
  );
}

function HoldForm({ onSubmit }: { onSubmit: (reason: string, remarks?: string) => void }) {
  const [reason, setReason] = useState(HOLD_REASONS[0].value);
  const [remarks, setRemarks] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(reason, remarks || undefined);
      }}
      className="space-y-2"
    >
      <SelectField
        label="Hold Reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        options={HOLD_REASONS.map((r) => ({ value: r.value, label: r.label }))}
      />
      <TextareaField label="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <Button type="submit" variant="secondary" size="sm" className="w-full">
        Place On Hold
      </Button>
    </form>
  );
}

function NoteForm({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        onSubmit(text.trim());
        setText("");
      }}
      className="flex items-end gap-2"
    >
      <div className="flex-1">
        <FormField label="Add a note" value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      <div className="mb-4">
        <SubmitButton>Add</SubmitButton>
      </div>
    </form>
  );
}

function RequestDocumentsForm({ documentTypes, onSubmit }: { documentTypes: NamedMasterData[]; onSubmit: (ids: string[]) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-3">
        {documentTypes.map((dt) => (
          <CheckboxField
            key={dt.id}
            label={dt.name}
            checked={selected.includes(dt.id)}
            onChange={(e) => setSelected((prev) => (e.target.checked ? [...prev, dt.id] : prev.filter((id) => id !== dt.id)))}
          />
        ))}
      </div>
      <Button variant="secondary" size="sm" disabled={selected.length === 0} onClick={() => onSubmit(selected)}>
        Request Selected Documents
      </Button>
    </div>
  );
}

function BankDetailsForm({ details, onSubmit }: { details: LoanCaseDetail["loan_details"]; onSubmit: (payload: Record<string, string>) => void }) {
  const [name, setName] = useState(details.bank_nbfc_name ?? "");
  const [appId, setAppId] = useState(details.bank_application_id ?? "");
  const [refNo, setRefNo] = useState(details.bank_reference_number ?? "");
  const [officer, setOfficer] = useState(details.assigned_officer ?? "");
  const [remarks, setRemarks] = useState(details.bank_remarks ?? "");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ bank_nbfc_name: name, bank_application_id: appId, bank_reference_number: refNo, assigned_officer: officer, bank_remarks: remarks });
      }}
    >
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <FormField label="Bank / NBFC Name" value={name} onChange={(e) => setName(e.target.value)} />
        <FormField label="Bank Application ID" value={appId} onChange={(e) => setAppId(e.target.value)} />
        <FormField label="Reference Number" value={refNo} onChange={(e) => setRefNo(e.target.value)} />
        <FormField label="Assigned Officer" value={officer} onChange={(e) => setOfficer(e.target.value)} />
      </div>
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <SubmitButton>Save Bank / NBFC Details</SubmitButton>
    </form>
  );
}

function DecisionForm({
  onSubmit,
  extraFields,
}: {
  onSubmit: (decision: "approved" | "rejected", rejectionReason: string | undefined, extra: { creditScore?: number; remarks?: string }) => void;
  extraFields: "credit" | "remarks";
}) {
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [creditScore, setCreditScore] = useState("");
  const [remarks, setRemarks] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [confirmReject, setConfirmReject] = useState(false);

  const submit = () => {
    onSubmit(decision, decision === "rejected" ? rejectionReason : undefined, {
      creditScore: creditScore ? Number(creditScore) : undefined,
      remarks: remarks || undefined,
    });
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
      {extraFields === "credit" && (
        <FormField label="Credit Score" type="number" value={creditScore} onChange={(e) => setCreditScore(e.target.value)} />
      )}
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

function OfferForm({ onSubmit }: { onSubmit: (payload: { offered_amount: number; offered_tenure_months: number; offered_interest_rate: number }) => void }) {
  const [amount, setAmount] = useState("");
  const [tenure, setTenure] = useState("");
  const [rate, setRate] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ offered_amount: Number(amount), offered_tenure_months: Number(tenure), offered_interest_rate: Number(rate) });
      }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField label="Amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        <FormField label="Tenure (months)" type="number" value={tenure} onChange={(e) => setTenure(e.target.value)} required />
        <FormField label="Interest Rate %" type="number" step="0.01" value={rate} onChange={(e) => setRate(e.target.value)} required />
      </div>
      <SubmitButton>Issue Offer</SubmitButton>
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
