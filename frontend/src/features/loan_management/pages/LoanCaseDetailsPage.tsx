import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
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
  const { caseId } = useParams<{ caseId: string }>();
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [documentTypes, setDocumentTypes] = useState<NamedMasterData[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <Section title="Case Overview">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <Field label="Customer" value={loanCase.customer_name} />
              <Field label="Product" value={loanCase.product_name} />
              <Field label="Assigned To" value={loanCase.assigned_to_name} />
              <Field label="Status" value={STATUS_LABELS[status] ?? status} />
            </div>
          </Section>

          <Section title="Bank / NBFC Details">
            <BankDetailsForm
              details={details}
              onSubmit={(payload) => run(() => recordBankDetails(caseId, payload), "Bank details updated.")}
            />
          </Section>

          {(status === "new_customer" || status === "documents_pending" || status === "additional_documents") && (
            <Section title="Document Verification">
              <p className="text-xs text-text/50">Pending: {loanCase.pending_document_type_ids.length === 0 ? "none requested" : loanCase.pending_document_type_ids.length}</p>
              <RequestDocumentsForm
                documentTypes={documentTypes}
                onSubmit={(ids) => run(() => requestLoanCaseDocuments(caseId, ids), "Documents requested.")}
              />
              {status !== "new_customer" && (
                <button type="button" onClick={() => run(() => verifyLoanCaseDocuments(caseId), "Documents verified.")} className="rounded bg-primary text-white text-sm font-medium py-2 px-4">
                  Verify Documents
                </button>
              )}
            </Section>
          )}

          {status === "credit_evaluation" && (
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
                <OfferForm onSubmit={(payload) => run(() => recordOffer(caseId, payload), "Offer issued.")} />
              ) : (
                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                  <Field label="Offered Amount" value={details.offered_amount} />
                  <Field label="Tenure (months)" value={details.offered_tenure_months} />
                  <Field label="Interest Rate" value={details.offered_interest_rate} />
                  <Field label="Customer Decision" value={details.offer_decision} />
                </div>
              )}
              <p className="text-xs text-text/40">Awaiting the Customer's own accept/decline action.</p>
            </Section>
          )}

          {status === "esign_nach_kyc" && (
            <Section title="eSign / NACH / KYC Checklist">
              <EsignNachKycForm
                details={details}
                onSubmit={(payload) => run(() => recordEsignNachKyc(caseId, payload), "eSign/NACH/KYC updated.")}
              />
            </Section>
          )}

          {status === "final_evaluation" && (
            <Section title="Decision Screen — Final Evaluation">
              <DecisionForm
                onSubmit={(decision, reason, extra) => run(() => recordFinalEvaluation(caseId, { remarks: extra.remarks, decision, rejection_reason: reason }), "Final evaluation recorded.")}
                extraFields="remarks"
              />
            </Section>
          )}

          {status === "send_for_disbursement" && (
            <Section title="Disbursement">
              <DisburseForm onSubmit={(payload) => run(() => disburseLoanCase(caseId, payload), "Loan disbursed.")} />
            </Section>
          )}

          {status === "disbursed" && (
            <Section title="Disbursement Record">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                <Field label="Disbursed Amount" value={details.disbursed_amount} />
                <Field label="Reference" value={details.disbursed_reference} />
                <Field label="Disbursed At" value={details.disbursed_at ? new Date(details.disbursed_at).toLocaleString() : null} />
              </div>
            </Section>
          )}
        </div>

        <div className="space-y-6">
          <Section title="Assignment">
            <AssignForm
              currentName={loanCase.assigned_to_name}
              onSubmit={(employeeId) => run(() => assignLoanCase(caseId, employeeId), "Case assigned.")}
            />
          </Section>

          {status !== "disbursed" && status !== "rejected" && (
            <Section title="Case Status Control">
              {status === "on_hold" ? (
                <button type="button" onClick={() => run(() => resumeLoanCase(caseId), "Case resumed.")} className="w-full rounded bg-primary text-white text-sm font-medium py-2">
                  Resume
                </button>
              ) : (
                <HoldForm onSubmit={(reason, remarks) => run(() => holdLoanCase(caseId, reason, remarks), "Case placed on hold.")} />
              )}
            </Section>
          )}

          <Section title="Application History">
            <NoteForm onSubmit={(text) => run(() => addLoanCaseNote(caseId, text), "Note added.")} />
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
    </SimplePageLayout>
  );
}

function AssignForm({ currentName, onSubmit }: { currentName: string | null; onSubmit: (employeeId: string) => void }) {
  const [employeeId, setEmployeeId] = useState("");
  return (
    <div className="space-y-2">
      {currentName && <p className="text-sm text-text/70">Currently: {currentName}</p>}
      <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} />
      <button type="button" disabled={!employeeId} onClick={() => onSubmit(employeeId)} className="w-full rounded bg-primary text-white text-sm font-medium py-2 disabled:opacity-50">
        {currentName ? "Reassign" : "Assign"}
      </button>
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
      <select value={reason} onChange={(e) => setReason(e.target.value)} className="w-full rounded border border-border px-3 py-2 text-sm">
        {HOLD_REASONS.map((r) => (
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </select>
      <textarea placeholder="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="w-full rounded border border-border px-3 py-2 text-sm" rows={2} />
      <button type="submit" className="w-full rounded border border-warning text-warning text-sm font-medium py-2">
        Place On Hold
      </button>
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
      className="flex gap-2"
    >
      <input type="text" placeholder="Add a note" value={text} onChange={(e) => setText(e.target.value)} className="flex-1 rounded border border-border px-3 py-2 text-sm" />
      <SubmitButton>Add</SubmitButton>
    </form>
  );
}

function RequestDocumentsForm({ documentTypes, onSubmit }: { documentTypes: NamedMasterData[]; onSubmit: (ids: string[]) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {documentTypes.map((dt) => (
          <label key={dt.id} className="flex items-center gap-1 text-xs border border-border rounded px-2 py-1">
            <input
              type="checkbox"
              checked={selected.includes(dt.id)}
              onChange={(e) => setSelected((prev) => (e.target.checked ? [...prev, dt.id] : prev.filter((id) => id !== dt.id)))}
            />
            {dt.name}
          </label>
        ))}
      </div>
      <button type="button" disabled={selected.length === 0} onClick={() => onSubmit(selected)} className="rounded border border-primary text-primary text-sm font-medium py-2 px-4 disabled:opacity-50">
        Request Selected Documents
      </button>
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
      className="grid grid-cols-2 gap-3"
    >
      <input placeholder="Bank / NBFC Name" value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <input placeholder="Bank Application ID" value={appId} onChange={(e) => setAppId(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <input placeholder="Reference Number" value={refNo} onChange={(e) => setRefNo(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <input placeholder="Assigned Officer" value={officer} onChange={(e) => setOfficer(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <textarea placeholder="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="col-span-2 rounded border border-border px-3 py-2 text-sm" rows={2} />
      <div className="col-span-2">
        <SubmitButton>Save Bank / NBFC Details</SubmitButton>
      </div>
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

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(decision, decision === "rejected" ? rejectionReason : undefined, {
          creditScore: creditScore ? Number(creditScore) : undefined,
          remarks: remarks || undefined,
        });
      }}
      className="space-y-3"
    >
      {extraFields === "credit" && (
        <input type="number" placeholder="Credit Score" value={creditScore} onChange={(e) => setCreditScore(e.target.value)} className="w-full rounded border border-border px-3 py-2 text-sm" />
      )}
      <textarea placeholder="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="w-full rounded border border-border px-3 py-2 text-sm" rows={2} />
      <div className="flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" checked={decision === "approved"} onChange={() => setDecision("approved")} /> Approve
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /> Reject
        </label>
      </div>
      {decision === "rejected" && (
        <textarea
          placeholder="Rejection reason (mandatory)"
          value={rejectionReason}
          onChange={(e) => setRejectionReason(e.target.value)}
          className="w-full rounded border border-border px-3 py-2 text-sm"
          rows={2}
        />
      )}
      <SubmitButton>Submit Decision</SubmitButton>
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
      className="grid grid-cols-3 gap-3"
    >
      <input type="number" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input type="number" placeholder="Tenure (months)" value={tenure} onChange={(e) => setTenure(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input type="number" step="0.01" placeholder="Interest Rate %" value={rate} onChange={(e) => setRate(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <div className="col-span-3">
        <SubmitButton>Issue Offer</SubmitButton>
      </div>
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
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={esign} onChange={(e) => setEsign(e.target.checked)} /> eSign completed</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={nach} onChange={(e) => setNach(e.target.checked)} /> NACH completed</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={kyc} onChange={(e) => setKyc(e.target.checked)} /> KYC completed</label>
      <SubmitButton>Save</SubmitButton>
    </form>
  );
}

function DisburseForm({ onSubmit }: { onSubmit: (payload: { disbursed_amount: number; disbursed_reference: string }) => void }) {
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ disbursed_amount: Number(amount), disbursed_reference: reference });
      }}
      className="grid grid-cols-2 gap-3"
    >
      <input type="number" placeholder="Disbursed Amount" value={amount} onChange={(e) => setAmount(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Reference / UTR" value={reference} onChange={(e) => setReference(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <div className="col-span-2">
        <SubmitButton>Mark Disbursed</SubmitButton>
      </div>
    </form>
  );
}
