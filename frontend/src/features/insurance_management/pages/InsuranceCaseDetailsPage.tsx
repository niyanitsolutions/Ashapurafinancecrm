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
  addInsuranceCaseNote,
  assignInsuranceCase,
  generatePolicy,
  getInsuranceCase,
  getInsuranceCaseTimeline,
  holdInsuranceCase,
  issuePolicy,
  recordMedicalVerification,
  recordPremium,
  recordUnderwriting,
  requestInsuranceCaseDocuments,
  resumeInsuranceCase,
  verifyInsuranceCaseDocuments,
  type CaseTimelineEntry,
  type InsuranceCaseDetail,
} from "@/features/insurance_management/api";
import { documentTypesApi, type NamedMasterData } from "@/features/system_settings/api";
import { HOLD_REASONS } from "@/features/workflow_engine/holdReasons";

const STATUS_LABELS: Record<string, string> = {
  application_submitted: "Application Submitted",
  documents_pending: "Documents Pending",
  underwriting: "Underwriting",
  medical_verification: "Medical Verification",
  additional_documents: "Additional Documents",
  premium_acceptance: "Premium Acceptance",
  policy_generation: "Policy Generation",
  policy_issued: "Policy Issued",
  on_hold: "On Hold",
  rejected: "Rejected",
};

function Field({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm">{value === null || value === undefined || value === "" ? "—" : String(value)}</div>
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

export function InsuranceCaseDetailsPage() {
  const { can } = usePermissions();
  // insurance_management:applications's real backend actions: view/edit/approve/
  // reject/assign — same pattern as Loan Management's mirror page. "edit" covers every
  // write below except Assign (assign) and Issue Policy (approve).
  const canEdit = can("insurance_management:applications", "edit");
  const canAssign = can("insurance_management:applications", "assign");
  const canIssuePolicy = can("insurance_management:applications", "approve");
  const { caseId } = useParams<{ caseId: string }>();
  const [insuranceCase, setInsuranceCase] = useState<InsuranceCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [documentTypes, setDocumentTypes] = useState<NamedMasterData[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmVerify, setConfirmVerify] = useState(false);
  const [confirmIssue, setConfirmIssue] = useState(false);

  const load = () => {
    if (!caseId) return;
    getInsuranceCase(caseId).then(setInsuranceCase).catch((err) => setError(getErrorMessage(err)));
    getInsuranceCaseTimeline(caseId).then(setTimeline).catch(() => setTimeline([]));
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

  if (error && !insuranceCase) {
    return (
      <SimplePageLayout title="Insurance Case" backTo="/insurance-cases">
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!insuranceCase) {
    return (
      <SimplePageLayout title="Insurance Case" backTo="/insurance-cases">
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  const status = insuranceCase.current_status;
  const details = insuranceCase.insurance_details;

  return (
    <SimplePageLayout title={`${insuranceCase.case_code} — ${STATUS_LABELS[status] ?? status}`} backTo="/insurance-cases">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      {insuranceCase.rejection_reason && (
        <div className="mb-4 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          Rejected — {insuranceCase.rejection_reason}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Section title="Case Overview">
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              <Field label="Customer" value={insuranceCase.customer_name} />
              <Field label="Product" value={insuranceCase.product_name} />
              <Field label="Assigned To" value={insuranceCase.assigned_to_name} />
              <Field label="Status" value={STATUS_LABELS[status] ?? status} />
            </div>
          </Section>

          {canEdit && (status === "application_submitted" || status === "documents_pending" || status === "additional_documents") && (
            <Section title="Document Verification">
              <p className="text-xs text-text/50">Pending: {insuranceCase.pending_document_type_ids.length === 0 ? "none requested" : insuranceCase.pending_document_type_ids.length}</p>
              <RequestDocumentsForm documentTypes={documentTypes} onSubmit={(ids) => run(() => requestInsuranceCaseDocuments(caseId, ids), "Documents requested.")} />
              {status !== "application_submitted" && (
                <Button size="sm" onClick={() => setConfirmVerify(true)}>
                  Verify Documents
                </Button>
              )}
            </Section>
          )}

          {canEdit && status === "underwriting" && (
            <Section title="Decision Screen — Underwriting">
              <UnderwritingForm onSubmit={(payload) => run(() => recordUnderwriting(caseId, payload), "Underwriting recorded.")} />
            </Section>
          )}

          {canEdit && status === "medical_verification" && (
            <Section title="Decision Screen — Medical Verification">
              <MedicalVerificationForm onSubmit={(payload) => run(() => recordMedicalVerification(caseId, payload), "Medical verification recorded.")} />
            </Section>
          )}

          {status === "premium_acceptance" && (
            <Section title="Premium Quote">
              {details.premium_amount == null ? (
                canEdit ? (
                  <PremiumForm onSubmit={(payload) => run(() => recordPremium(caseId, payload), "Premium quote issued.")} />
                ) : (
                  <p className="text-sm text-text/40">No premium quote issued yet.</p>
                )
              ) : (
                <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                  <Field label="Premium Amount" value={details.premium_amount} />
                  <Field label="Customer Decision" value={details.premium_decision} />
                </div>
              )}
              <p className="text-xs text-text/40">Awaiting the Customer's own accept/decline action.</p>
            </Section>
          )}

          {status === "policy_generation" && (
            <Section title="Policy Generation">
              {details.policy_number == null ? (
                canEdit ? (
                  <GeneratePolicyForm onSubmit={(payload) => run(() => generatePolicy(caseId, payload), "Policy number generated.")} />
                ) : (
                  <p className="text-sm text-text/40">No policy number generated yet.</p>
                )
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                    <Field label="Policy Number" value={details.policy_number} />
                    <Field label="Generated At" value={details.policy_generated_at ? new Date(details.policy_generated_at).toLocaleString() : null} />
                  </div>
                  {canIssuePolicy && (
                    <Button size="sm" onClick={() => setConfirmIssue(true)}>
                      Issue Policy
                    </Button>
                  )}
                </>
              )}
            </Section>
          )}

          {status === "policy_issued" && (
            <Section title="Policy">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Policy Number" value={details.policy_number} />
                <Field label="Issued At" value={details.policy_issued_at ? new Date(details.policy_issued_at).toLocaleString() : null} />
              </div>
            </Section>
          )}
        </div>

        <div className="space-y-6">
          {canAssign && (
            <Section title="Assignment">
              <AssignForm currentName={insuranceCase.assigned_to_name} onSubmit={(employeeId) => run(() => assignInsuranceCase(caseId, employeeId), "Case assigned.")} />
            </Section>
          )}

          {canEdit && status !== "policy_issued" && status !== "rejected" && (
            <Section title="Case Status Control">
              {status === "on_hold" ? (
                <Button size="sm" className="w-full" onClick={() => run(() => resumeInsuranceCase(caseId), "Case resumed.")}>
                  Resume
                </Button>
              ) : (
                <HoldForm onSubmit={(reason, remarks) => run(() => holdInsuranceCase(caseId, reason, remarks), "Case placed on hold.")} />
              )}
            </Section>
          )}

          <Section title="Application History">
            {canEdit && <NoteForm onSubmit={(text) => run(() => addInsuranceCaseNote(caseId, text), "Note added.")} />}
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
          await run(() => verifyInsuranceCaseDocuments(caseId), "Documents verified.");
          setConfirmVerify(false);
        }}
        onClose={() => setConfirmVerify(false)}
      />
      <ConfirmDialog
        open={confirmIssue}
        title="Issue Policy"
        message="Issue this policy? Once issued, the case moves to Policy Issued and this cannot be undone here."
        confirmLabel="Issue Policy"
        onConfirm={async () => {
          await run(() => issuePolicy(caseId), "Policy issued.");
          setConfirmIssue(false);
        }}
        onClose={() => setConfirmIssue(false)}
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

function UnderwritingForm({
  onSubmit,
}: {
  onSubmit: (payload: {
    sum_insured?: number; underwriting_remarks?: string; requires_medical: boolean; requires_additional_documents: boolean;
    decision: "approved" | "rejected"; rejection_reason?: string;
  }) => void;
}) {
  const [sumInsured, setSumInsured] = useState("");
  const [remarks, setRemarks] = useState("");
  const [requiresMedical, setRequiresMedical] = useState(false);
  const [requiresAdditionalDocuments, setRequiresAdditionalDocuments] = useState(false);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [rejectionReason, setRejectionReason] = useState("");
  const [confirmReject, setConfirmReject] = useState(false);

  const submit = () => {
    onSubmit({
      sum_insured: sumInsured ? Number(sumInsured) : undefined, underwriting_remarks: remarks || undefined,
      requires_medical: requiresMedical, requires_additional_documents: requiresAdditionalDocuments,
      decision, rejection_reason: decision === "rejected" ? rejectionReason : undefined,
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
      <FormField label="Sum Insured" type="number" value={sumInsured} onChange={(e) => setSumInsured(e.target.value)} />
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <CheckboxField label="Requires medical verification" checked={requiresMedical} onChange={(e) => setRequiresMedical(e.target.checked)} />
      <CheckboxField label="Requires additional documents" checked={requiresAdditionalDocuments} onChange={(e) => setRequiresAdditionalDocuments(e.target.checked)} />
      <div className="flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={decision === "approved"} onChange={() => setDecision("approved")} /> Approve</label>
        <label className="flex items-center gap-2"><input type="radio" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /> Reject</label>
      </div>
      {decision === "rejected" && (
        <TextareaField label="Rejection reason (mandatory)" value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} rows={2} required />
      )}
      <SubmitButton>Submit Decision</SubmitButton>

      <ConfirmDialog
        open={confirmReject}
        title="Reject Case"
        message="Reject this case at underwriting? This decision is recorded on the case history and cannot be undone here."
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

function MedicalVerificationForm({ onSubmit }: { onSubmit: (payload: { outcome: "cleared" | "failed"; medical_remarks?: string; rejection_reason?: string }) => void }) {
  const [outcome, setOutcome] = useState<"cleared" | "failed">("cleared");
  const [remarks, setRemarks] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [confirmFail, setConfirmFail] = useState(false);

  const submit = () => {
    onSubmit({ outcome, medical_remarks: remarks || undefined, rejection_reason: outcome === "failed" ? rejectionReason : undefined });
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (outcome === "failed") {
          setConfirmFail(true);
          return;
        }
        submit();
      }}
      className="space-y-3"
    >
      <TextareaField label="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <div className="flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={outcome === "cleared"} onChange={() => setOutcome("cleared")} /> Cleared</label>
        <label className="flex items-center gap-2"><input type="radio" checked={outcome === "failed"} onChange={() => setOutcome("failed")} /> Failed</label>
      </div>
      {outcome === "failed" && (
        <TextareaField label="Rejection reason (mandatory)" value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} rows={2} required />
      )}
      <SubmitButton>Submit Decision</SubmitButton>

      <ConfirmDialog
        open={confirmFail}
        title="Mark Medical Verification Failed"
        message="Mark this case as failed medical verification and reject it? This is recorded on the case history and cannot be undone here."
        confirmLabel="Confirm Failed"
        confirmVariant="danger"
        onConfirm={() => {
          submit();
          setConfirmFail(false);
        }}
        onClose={() => setConfirmFail(false)}
      />
    </form>
  );
}

function PremiumForm({ onSubmit }: { onSubmit: (payload: { premium_amount: number }) => void }) {
  const [amount, setAmount] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ premium_amount: Number(amount) });
      }}
      className="flex items-end gap-3"
    >
      <div className="flex-1">
        <FormField label="Premium Amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} required />
      </div>
      <div className="mb-4">
        <SubmitButton>Issue Premium Quote</SubmitButton>
      </div>
    </form>
  );
}

function GeneratePolicyForm({ onSubmit }: { onSubmit: (payload: { policy_number: string }) => void }) {
  const [policyNumber, setPolicyNumber] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ policy_number: policyNumber });
      }}
      className="flex items-end gap-3"
    >
      <div className="flex-1">
        <FormField label="Policy Number" value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} required />
      </div>
      <div className="mb-4">
        <SubmitButton>Generate Policy</SubmitButton>
      </div>
    </form>
  );
}
