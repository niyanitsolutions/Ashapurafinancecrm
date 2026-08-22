import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addLoanCaseNote,
  assignLoanCase,
  getLoanCase,
  getLoanCaseTimeline,
  holdLoanCase,
  resumeLoanCase,
  type CaseTimelineEntry,
  type LoanCaseDetail,
} from "@/features/loan_management/api";
import { UpdateLoanCaseModal } from "@/features/loan_management/components/UpdateLoanCaseModal";
import { LOAN_STATUS_LABELS as STATUS_LABELS } from "@/features/loan_management/constants";
import { documentTypesApi, type NamedMasterData } from "@/features/system_settings/api";
import { formatISTDateTime } from "@/shared/dateFormat";
import { useDocumentCollectionBackContext } from "@/shared/navigationContext";
import { HOLD_REASONS } from "@/features/workflow_engine/holdReasons";

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
  // Reached via StaffApplicationDetailsPage's "Manage Status ->" link, which propagates
  // the Document Collection context forward when present — every normal Loan
  // Management -> Loan Cases -> View entry point keeps the original default.
  const { backTo, backLabel } = useDocumentCollectionBackContext("/loan-cases");
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [documentTypes, setDocumentTypes] = useState<NamedMasterData[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpdateModal, setShowUpdateModal] = useState(false);

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
      <SimplePageLayout title="Loan Case" backTo={backTo} backLabel={backLabel}>
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!loanCase) {
    return (
      <SimplePageLayout title="Loan Case" backTo={backTo} backLabel={backLabel}>
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  const status = loanCase.current_status;
  const details = loanCase.loan_details;
  const canUpdate = (canEdit || canDisburse) && status !== "disbursed" && status !== "rejected";

  return (
    <SimplePageLayout
      title={`${loanCase.case_code} — ${STATUS_LABELS[status] ?? status}`}
      backTo={backTo}
      backLabel={backLabel}
      actions={canUpdate && <Button onClick={() => setShowUpdateModal(true)}>Update</Button>}
    >
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

          {(details.credit_score != null || details.credit_remarks) && (
            <Section title="Credit Evaluation">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Credit Score" value={details.credit_score} />
                <Field label="Remarks" value={details.credit_remarks} />
              </div>
            </Section>
          )}

          {(loanCase.selected_bank_name || loanCase.approved_amount != null) && (
            <Section title="Offer">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Selected Bank / NBFC" value={loanCase.selected_bank_name} />
                <Field label="Approved Amount" value={loanCase.approved_amount != null ? `₹${loanCase.approved_amount.toLocaleString("en-IN")}` : null} />
              </div>
            </Section>
          )}

          {details.rv_ov_ref_type != null && (
            <Section title="RV / OV / Ref">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Verification Type" value={details.rv_ov_ref_type} />
                <Field label="Verification Status" value={details.rv_ov_ref_status} />
                <Field label="Verification Date" value={details.rv_ov_ref_date ? formatISTDateTime(details.rv_ov_ref_date) : null} />
                <Field label="Verified By" value={details.rv_ov_ref_verified_by} />
                <Field label="Result" value={details.rv_ov_ref_result} />
                <Field label="Remarks" value={details.rv_ov_ref_remarks} />
              </div>
            </Section>
          )}

          {(details.esign_completed || details.nach_completed || details.kyc_completed) && (
            <Section title="eSign / NACH / KYC">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-3">
                <Field label="eSign" value={details.esign_completed ? "Completed" : "Pending"} />
                <Field label="NACH" value={details.nach_completed ? "Completed" : "Pending"} />
                <Field label="KYC" value={details.kyc_completed ? "Completed" : "Pending"} />
              </div>
            </Section>
          )}

          {details.final_evaluation_remarks != null && (
            <Section title="Final Evaluation">
              <Field label="Remarks" value={details.final_evaluation_remarks} />
            </Section>
          )}

          {status === "disbursed" && (
            <Section title="Disbursement Record">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Disbursed Amount" value={details.disbursed_amount} />
                <Field label="Reference" value={details.disbursed_reference} />
                <Field label="Disbursed At" value={details.disbursed_at ? formatISTDateTime(details.disbursed_at) : null} />
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
                  <div className="text-xs text-text/40">{formatISTDateTime(entry.created_at)}</div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>

      {showUpdateModal && (
        <UpdateLoanCaseModal
          caseId={caseId}
          loanCase={loanCase}
          documentTypes={documentTypes}
          canEdit={canEdit}
          canDisburse={canDisburse}
          onClose={() => setShowUpdateModal(false)}
          onUpdated={load}
        />
      )}
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

