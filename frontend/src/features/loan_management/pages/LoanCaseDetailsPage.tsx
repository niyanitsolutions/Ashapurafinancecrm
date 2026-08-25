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
import { DocumentChecklist } from "@/features/customer/components/DocumentChecklist";
import { getFormDefinition, listDocuments, type ApplicationDocument, type RequiredDocument } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addLoanCaseNote,
  assignLoanCase,
  getLoanCase,
  getLoanCaseTimeline,
  holdLoanCase,
  listAdditionalDocuments,
  resumeLoanCase,
  type AdditionalDocument,
  type CaseTimelineEntry,
  type LoanCaseDetail,
} from "@/features/loan_management/api";
import { UpdateLoanCaseModal } from "@/features/loan_management/components/UpdateLoanCaseModal";
import { LOAN_STATUS_LABELS as STATUS_LABELS } from "@/features/loan_management/constants";
import { formatISTDateTime } from "@/shared/dateFormat";
import { useDocumentCollectionBackContext } from "@/shared/navigationContext";
import { HOLD_REASONS } from "@/features/workflow_engine/holdReasons";

const ADDITIONAL_DOC_STATUS_LABELS: Record<string, string> = { pending: "Pending Review", verified: "Verified", rejected: "Rejected" };

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
  // Management -> Loan Cases -> View entry point keeps the original default, now the
  // canonical /loan-management/cases route (decision #132).
  const { backTo, backLabel } = useDocumentCollectionBackContext("/loan-management/cases");
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  // Requirement 22-24 — the complete application view: every document already uploaded
  // during Document Collection (before this case ever reached Loan Management), plus
  // this case's own Additional Documents. Reuses the SAME staff document endpoint/
  // component StaffApplicationDetailsPage already uses — no second document mechanism.
  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [requiredDocuments, setRequiredDocuments] = useState<RequiredDocument[]>([]);
  const [additionalDocuments, setAdditionalDocuments] = useState<AdditionalDocument[]>([]);

  const load = () => {
    if (!caseId) return;
    getLoanCase(caseId).then(setLoanCase).catch((err) => setError(getErrorMessage(err)));
    getLoanCaseTimeline(caseId).then(setTimeline).catch(() => setTimeline([]));
    listAdditionalDocuments(caseId).then(setAdditionalDocuments).catch(() => setAdditionalDocuments([]));
  };

  useEffect(load, [caseId]);

  const applicationId = loanCase?.application_id;
  const productId = loanCase?.product_id;
  useEffect(() => {
    if (!applicationId || !productId) return;
    listDocuments(applicationId).then(setDocuments).catch(() => setDocuments([]));
    getFormDefinition("loan", productId)
      .then((def) => setRequiredDocuments(def.required_documents))
      .catch(() => setRequiredDocuments([]));
  }, [applicationId, productId]);

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
              <Field label="Case Code" value={loanCase.case_code} />
              <Field label="Customer" value={loanCase.customer_name} />
              <Field label="Product" value={loanCase.product_name} />
              <Field label="Assigned To" value={loanCase.assigned_to_name} />
              <Field label="Current Status" value={STATUS_LABELS[status] ?? status} />
            </div>
          </Section>

          {loanCase.customer && (
            <Section title="Customer Details">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Name" value={loanCase.customer.full_name} />
                <Field label="Mobile" value={loanCase.customer.mobile} />
                <Field label="Email" value={loanCase.customer.email} />
                <Field label="Date of Birth" value={loanCase.customer.date_of_birth ? formatISTDateTime(loanCase.customer.date_of_birth) : null} />
                <Field
                  label="Address"
                  value={
                    [loanCase.customer.address_line1, loanCase.customer.address_line2, loanCase.customer.city, loanCase.customer.state, loanCase.customer.pincode]
                      .filter(Boolean)
                      .join(", ") || null
                  }
                />
              </div>
            </Section>
          )}

          {loanCase.application && (
            <Section title="Application">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Application Number" value={loanCase.application.application_code} />
                <Field label="Product" value={loanCase.product_name} />
                <Field label="Requested Amount" value={details.requested_amount != null ? `₹${details.requested_amount.toLocaleString("en-IN")}` : null} />
                <Field label="Current Stage" value={STATUS_LABELS[status] ?? status} />
                <Field label="Application Status" value={loanCase.application.status} />
                <Field label="Submitted At" value={loanCase.application.submitted_at ? formatISTDateTime(loanCase.application.submitted_at) : null} />
              </div>
            </Section>
          )}

          {loanCase.bank_offers.length > 0 ? (
            <Section title="Bank / NBFC Offers">
              <div className="space-y-3">
                {loanCase.bank_offers.map((offer) => (
                  <div key={offer.id} className="rounded border border-border p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-text">{offer.bank_name}</span>
                      {offer.is_selected && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-semibold text-primary">Selected</span>}
                    </div>
                    <div className="text-xs text-text/50">
                      {offer.branch && <span>Branch: {offer.branch} </span>}
                      {offer.loan_type && <span>Loan Type: {offer.loan_type} </span>}
                      {offer.requested_amount != null && <span>Requested Amount: ₹{offer.requested_amount.toLocaleString("en-IN")}</span>}
                    </div>
                    {offer.remarks && <div className="text-xs text-text/50">Remarks: {offer.remarks}</div>}
                    {offer.decision !== "pending" && (
                      <div className="text-sm text-text/70">
                        Bank Decision: {offer.decision === "approved" ? "Approved" : "Rejected / Re-Eligible"}
                        {offer.decision === "approved" && (
                          <div className="mt-1 text-xs text-text/50">
                            {offer.approved_amount != null && <span>Approved Amount: ₹{offer.approved_amount.toLocaleString("en-IN")} </span>}
                            {offer.interest_rate != null && <span>Interest Rate: {offer.interest_rate}% </span>}
                            {offer.tenure_months != null && <span>Tenure: {offer.tenure_months} months </span>}
                            {offer.processing_fee != null && <span>Processing Fee: ₹{offer.processing_fee.toLocaleString("en-IN")} </span>}
                            {offer.emi_per_month != null && <span>EMI Per Month: ₹{offer.emi_per_month.toLocaleString("en-IN")}</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          ) : (
            (details.preferred_bank_name || details.preferred_branch || details.loan_type || details.requested_amount != null) && (
              <Section title="New Customer Preferences">
                <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                  <Field label="Preferred Bank / NBFC" value={details.preferred_bank_name} />
                  <Field label="Preferred Branch" value={details.preferred_branch} />
                  <Field label="Loan Type" value={details.loan_type} />
                  <Field label="Requested Amount" value={details.requested_amount != null ? `₹${details.requested_amount.toLocaleString("en-IN")}` : null} />
                  <Field label="Remarks" value={details.preferred_remarks} />
                </div>
              </Section>
            )
          )}

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

          {/* Requirement 22-24: every document already uploaded during Document
              Collection stays visible here — the SAME staff document endpoint/component
              StaffApplicationDetailsPage uses, read-only (no upload dropzone). */}
          <Section title="Documents">
            {requiredDocuments.length > 0 ? (
              <DocumentChecklist requiredDocuments={requiredDocuments} uploadedDocuments={documents} onUpload={() => {}} uploadingFor={null} disabled />
            ) : (
              <p className="text-sm text-text/40">No documents on file for this application yet.</p>
            )}
          </Section>

          {additionalDocuments.length > 0 && (
            <Section title="Additional Documents">
              <div className="space-y-2">
                {additionalDocuments.map((doc) => (
                  <div key={doc.id} className="rounded border border-border p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-text">{doc.name}</span>
                      <span className="text-xs text-text/50">
                        {doc.document_status === "requested" ? "Pending Upload" : ADDITIONAL_DOC_STATUS_LABELS[doc.verification_status]}
                      </span>
                    </div>
                    {doc.verification_status === "rejected" && doc.rejection_reason && (
                      <p className="text-xs text-danger">Reason: {doc.rejection_reason}</p>
                    )}
                    {doc.uploaded_at && <p className="text-xs text-text/40">Uploaded: {formatISTDateTime(doc.uploaded_at)}</p>}
                    {(doc.download_url || doc.attachment_url) && (
                      <div className="flex gap-2 pt-1">
                        {doc.download_url && (
                          <a href={doc.download_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
                            Preview
                          </a>
                        )}
                        {doc.attachment_url && (
                          <a href={doc.attachment_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
                            Download
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                ))}
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

