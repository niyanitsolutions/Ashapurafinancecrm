import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { usePermissions } from "@/features/access_control/usePermissions";
import { uploadApplicationDocument, type ApplicationDocument } from "@/features/customer/api";
import { DocumentChecklist } from "@/features/customer/components/DocumentChecklist";
import { getErrorMessage } from "@/features/customer/errors";
import { useProductSchema } from "@/features/customer/useProductSchema";
import { AddOtherDocumentPanel } from "@/features/insurance_management/components/AddOtherDocumentPanel";
import {
  PaymentUpdateModal,
  type PaymentUpdatePayload,
} from "@/features/insurance_management/components/PaymentUpdateModal";
import {
  PolicyLoginUpdateModal,
  type PolicyLoginUpdatePayload,
} from "@/features/insurance_management/components/PolicyLoginUpdateModal";
import {
  RejectInsuranceCaseModal,
  type RejectInsuranceCasePayload,
} from "@/features/insurance_management/components/RejectInsuranceCaseModal";
import {
  addInsuranceCaseNote,
  assignInsuranceCase,
  getInsuranceCase,
  getInsuranceCaseTimeline,
  holdInsuranceCase,
  listInsuranceCaseDocuments,
  moveInsuranceCaseBack,
  moveInsuranceCaseToStage,
  moveToPayment,
  moveToPolicyDocument,
  moveToPolicyIssued,
  moveToPolicyLogin,
  rejectInsuranceCase,
  rejectInsuranceCaseDocument,
  restartFromReEligible,
  resumeInsuranceCase,
  updatePayment,
  updatePolicyLogin,
  verifyInsuranceCaseDocument,
  type CaseTimelineEntry,
  type InsuranceApplicantDetails,
  type InsuranceCaseDetail,
  type InsuranceCaseDocument,
} from "@/features/insurance_management/api";
import {
  getInsuranceStatusControlInfo,
  INSURANCE_HOLD_REASON_LABELS,
  INSURANCE_HOLD_REASONS,
  INSURANCE_PAYMENT_STATUS_LABELS,
  INSURANCE_STATUS_LABELS,
} from "@/features/insurance_management/statusControl";
import { listAdvisors, type AdvisorListItem } from "@/features/recruitment/api";
import { ADVISOR_CHANNEL_LABELS } from "@/features/recruitment/labels";

// Every stage staff can deliberately "Move To" — the backend still validates the case
// can legally exist there (documents verified, premium recorded, fully paid + Issue Date, …).
const MOVE_TO_STAGES = ["fresh_lead", "policy_document", "policy_login", "payment", "policy_issued", "re_eligible", "rejected"];
import { formatISTDate, formatISTDateTime } from "@/shared/dateFormat";
import { useDocumentCollectionBackContext } from "@/shared/navigationContext";

const STATUS_LABELS = INSURANCE_STATUS_LABELS;

function formatINR(value: number | null | undefined): string {
  if (value == null) return "—";
  return `₹${value.toLocaleString("en-IN")}`;
}

// "testing001 — QR" — the assigned Advisor's name plus their Type, when both are known.
// `channel` is `null` for an unassigned case or a legacy employee-id assignment (no
// Advisor Type concept), in which case only the name is shown.
function advisorDisplayName(name: string | null, channel: string | null): string | null {
  if (!name) return null;
  if (!channel) return name;
  return `${name} — ${ADVISOR_CHANNEL_LABELS[channel] ?? channel}`;
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
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
  const canEdit = can("insurance_management:applications", "edit");
  const canAssign = can("insurance_management:applications", "assign");
  const canIssuePolicy = can("insurance_management:applications", "approve");
  const canReject = canEdit || can("insurance_management:applications", "reject");
  const { caseId } = useParams<{ caseId: string }>();
  const { backTo, backLabel } = useDocumentCollectionBackContext("/insurance-management/fresh-leads");

  const [insuranceCase, setInsuranceCase] = useState<InsuranceCaseDetail | null>(null);
  const [timeline, setTimeline] = useState<CaseTimelineEntry[]>([]);
  const [documents, setDocuments] = useState<InsuranceCaseDocument[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejectingDoc, setRejectingDoc] = useState<ApplicationDocument | null>(null);
  const [rejectDocReason, setRejectDocReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [showPolicyLogin, setShowPolicyLogin] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmIssue, setConfirmIssue] = useState(false);
  const [moveTarget, setMoveTarget] = useState("");
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);

  const { data: formDef } = useProductSchema("insurance", insuranceCase?.product_id);

  const load = () => {
    if (!caseId) return;
    getInsuranceCase(caseId)
      .then(setInsuranceCase)
      .catch((err) => setError(getErrorMessage(err)));
    getInsuranceCaseTimeline(caseId).then(setTimeline).catch(() => setTimeline([]));
    listInsuranceCaseDocuments(caseId).then(setDocuments).catch(() => setDocuments([]));
  };

  useEffect(load, [caseId]);

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
      <SimplePageLayout title="Insurance Case" backTo={backTo} backLabel={backLabel}>
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!insuranceCase) {
    return (
      <SimplePageLayout title="Insurance Case" backTo={backTo} backLabel={backLabel}>
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  const status = insuranceCase.current_status;
  const details = insuranceCase.insurance_details;
  const docSummary = insuranceCase.required_documents;
  const control = getInsuranceStatusControlInfo(status);
  const orphanDocs = documents.filter((d) => !d.is_in_schema);
  const premiumReady = details.premium_amount != null && details.ppt != null && details.pt != null;

  // Staff-side document upload / re-upload for the pinned Product Schema checklist —
  // reuses the exact same product-agnostic endpoint the Staff Application view already
  // uses (`POST /applications/{id}/documents/upload-url` + confirm, staff-authorised via
  // `get_application_for_staff`). `confirm_document` supersedes any prior version
  // (`replaces_document_id` + `is_current`), so a re-upload after a rejection keeps the
  // rejected one in history and makes the new file the current, pending-review one.
  const onUploadDocument = async (documentTypeId: string, file: File, password?: string, side?: string) => {
    if (!insuranceCase) return;
    setError(null);
    setMessage(null);
    setUploadingFor(documentTypeId);
    try {
      await uploadApplicationDocument(insuranceCase.application_id, documentTypeId, file, password, side);
      setMessage("Document uploaded.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploadingFor(null);
    }
  };

  const onVerifyDoc = (documentId: string) => run(() => verifyInsuranceCaseDocument(caseId, documentId), "Document verified.");
  const onRejectDoc = async () => {
    if (!rejectingDoc || !rejectDocReason.trim()) return;
    await run(() => rejectInsuranceCaseDocument(caseId, rejectingDoc.id, rejectDocReason.trim()), "Document rejected.");
    setRejectingDoc(null);
    setRejectDocReason("");
  };

  const documentExtraActions = (doc: ApplicationDocument) =>
    canEdit && doc.verification_status === "pending" && doc.document_status === "uploaded" ? (
      <>
        <button type="button" onClick={() => onVerifyDoc(doc.id)} className="text-xs font-medium text-success hover:underline">
          Verify
        </button>
        <button type="button" onClick={() => setRejectingDoc(doc)} className="text-xs font-medium text-danger hover:underline">
          Reject
        </button>
      </>
    ) : null;

  const doReject = async (payload: RejectInsuranceCasePayload) => {
    setSubmitting(true);
    setError(null);
    try {
      await rejectInsuranceCase(caseId, payload);
      setShowReject(false);
      setMessage("Case rejected.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const doPolicyLogin = async (payload: PolicyLoginUpdatePayload) => {
    setSubmitting(true);
    setError(null);
    try {
      await updatePolicyLogin(caseId, payload);
      setShowPolicyLogin(false);
      setMessage("Policy Login updated.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const doPayment = async (payload: PaymentUpdatePayload) => {
    setSubmitting(true);
    setError(null);
    try {
      await updatePayment(caseId, payload);
      setShowPayment(false);
      setMessage("Payment updated.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SimplePageLayout title={`${insuranceCase.case_code} — ${STATUS_LABELS[status] ?? status}`} backTo={backTo} backLabel={backLabel}>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      {status === "rejected" && insuranceCase.rejection_reason && (
        <div className="mb-4 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          Rejected — {insuranceCase.rejection_reason}
          {details.re_eligibility_choice && details.re_eligibility_choice !== "no" && details.re_eligible_date && (
            <> · Re-Eligible from {formatISTDateTime(details.re_eligible_date)}</>
          )}
          {details.re_eligibility_choice === "no" && <> · Not scheduled to become Re-Eligible</>}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Section title="Case Overview">
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              <Field label="Customer" value={insuranceCase.customer_name} />
              <Field label="Product" value={insuranceCase.product_name} />
              <Field label="Category" value={formDef?.insurance_category_name} />
              <Field
                label="Assigned Advisor"
                value={advisorDisplayName(insuranceCase.assigned_to_name, insuranceCase.assigned_to_channel)}
              />
              <Field label="Status" value={STATUS_LABELS[status] ?? status} />
              <Field label="Created" value={formatISTDateTime(insuranceCase.created_at)} />
            </div>
          </Section>

          <ApplicantDetailsSection applicant={insuranceCase.applicant} />

          {canEdit && status !== "policy_issued" && status !== "rejected" && status !== "on_hold" && (
            <Section title="Move Case Forward">
              {status === "fresh_lead" && control.kind === "simple" && (
                <div className="flex items-center justify-between gap-3 rounded border border-border bg-background/50 px-3 py-2">
                  <span className="text-sm text-text/70">Next: <span className="font-medium text-text">Policy Document</span></span>
                  <Button size="sm" onClick={() => run(() => moveToPolicyDocument(caseId), "Moved to Policy Document.")}>
                    Move to Policy Document
                  </Button>
                </div>
              )}

              {status === "policy_document" && (
                <div className="space-y-2">
                  <p className="text-sm text-text/70">
                    {docSummary.verified_total} / {docSummary.required_total} required documents verified.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      disabled={!docSummary.all_required_verified}
                      onClick={() => run(() => moveToPolicyLogin(caseId), "Moved to Policy Login.")}
                    >
                      Move to Policy Login
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => run(() => moveInsuranceCaseBack(caseId, "fresh_lead"), "Moved back to Fresh Lead.")}>
                      Move Back to Fresh Lead
                    </Button>
                  </div>
                  {!docSummary.all_required_verified && (
                    <p className="text-xs text-text/50">Every required document must be verified before moving to Policy Login.</p>
                  )}
                </div>
              )}

              {status === "policy_login" && (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                    <Field label="Premium" value={formatINR(details.premium_amount)} />
                    <Field label="Policy Number" value={details.policy_number} />
                    <Field label="PPT (years)" value={details.ppt} />
                    <Field label="PT (years)" value={details.pt} />
                    <Field label="Issue Date" value={details.policy_issue_date ? formatISTDate(details.policy_issue_date) : null} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => setShowPolicyLogin(true)}>
                      Update Premium / PPT / PT
                    </Button>
                    {canEdit && (
                      <Button size="sm" disabled={!premiumReady} onClick={() => run(() => moveToPayment(caseId), "Moved to Payment.")}>
                        Move to Payment
                      </Button>
                    )}
                    <Button size="sm" variant="secondary" onClick={() => run(() => moveInsuranceCaseBack(caseId, "policy_document"), "Moved back to Policy Document.")}>
                      Move Back to Policy Document
                    </Button>
                  </div>
                  {!premiumReady && <p className="text-xs text-text/50">Record Premium, PPT and PT before moving to Payment.</p>}
                </div>
              )}

              {status === "payment" && (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                    <Field label="Premium Amount" value={formatINR(details.premium_amount)} />
                    <Field label="Amount Paid" value={formatINR(details.amount_paid)} />
                    <Field
                      label="Balance"
                      value={
                        details.premium_amount != null && details.amount_paid != null
                          ? formatINR(details.premium_amount - details.amount_paid)
                          : null
                      }
                    />
                    <Field
                      label="Payment Status"
                      value={details.payment_status ? INSURANCE_PAYMENT_STATUS_LABELS[details.payment_status] : null}
                    />
                    <Field label="Issue Date" value={details.policy_issue_date ? formatISTDate(details.policy_issue_date) : null} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => setShowPayment(true)}>
                      Update Payment
                    </Button>
                    {canIssuePolicy && (
                      <Button
                        size="sm"
                        disabled={
                          details.payment_status !== "fully_paid" ||
                          details.premium_amount == null ||
                          details.amount_paid == null ||
                          details.amount_paid < details.premium_amount ||
                          details.policy_issue_date == null
                        }
                        onClick={() => setConfirmIssue(true)}
                      >
                        Move to Policy Issued
                      </Button>
                    )}
                    <Button size="sm" variant="secondary" onClick={() => run(() => moveInsuranceCaseBack(caseId, "policy_login"), "Moved back to Policy Login.")}>
                      Move Back to Policy Login
                    </Button>
                  </div>
                  {details.payment_status !== "fully_paid" && (
                    <p className="text-xs text-text/50">The Premium Amount must be fully paid before issuing the policy.</p>
                  )}
                  {details.payment_status === "fully_paid" && details.policy_issue_date == null && (
                    <p className="text-xs text-text/50">Record the Issue Date (Policy Login → Update) before issuing the policy.</p>
                  )}
                </div>
              )}

              {status === "re_eligible" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => run(() => restartFromReEligible(caseId, "fresh_lead"), "Restarted at Fresh Lead.")}>
                    Restart at Fresh Lead
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => run(() => restartFromReEligible(caseId, "policy_document"), "Restarted at Policy Document.")}>
                    Restart at Policy Document
                  </Button>
                </div>
              )}

              {canReject && status !== "re_eligible" && (
                <div className="pt-1">
                  <Button size="sm" variant="danger" onClick={() => setShowReject(true)}>
                    Reject Case
                  </Button>
                </div>
              )}
            </Section>
          )}

          {(status === "policy_document" || status === "policy_login" || status === "policy_issued") && (
            <Section title="Documents">
              {formDef ? (
                <DocumentChecklist
                  requiredDocuments={formDef.required_documents}
                  uploadedDocuments={documents}
                  onUpload={onUploadDocument}
                  uploadingFor={uploadingFor}
                  // Upload / re-upload is a Policy Document-stage action. At Policy Login /
                  // Policy Issued the checklist is read-only (Verify/Reject still available
                  // via extraActions for anything still pending).
                  disabled={!canEdit || status !== "policy_document"}
                  extraActions={documentExtraActions}
                />
              ) : (
                <p className="text-sm text-text/50">Loading…</p>
              )}

              {orphanDocs.length > 0 && (
                <div className="mt-4 border-t border-border pt-3">
                  <h4 className="text-xs font-semibold text-text/50">Previously Uploaded (not in the current product's schema)</h4>
                  <ul className="mt-2 space-y-1">
                    {orphanDocs.map((d) => (
                      <li key={d.id} className="flex items-center gap-2 text-sm">
                        <span className="text-text">{d.document_type_name}</span>
                        {d.download_url && (
                          <a href={d.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline text-xs">
                            Preview
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Section>
          )}

          {canEdit && (status === "policy_document" || status === "policy_login") && (
            <Section title="Other Documents">
              <AddOtherDocumentPanel caseId={caseId} canEdit={canEdit} />
            </Section>
          )}

          {status === "policy_issued" && (
            <Section title="Policy">
              <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
                <Field label="Policy Number" value={details.policy_number} />
                <Field label="Issue Date" value={details.policy_issue_date ? formatISTDate(details.policy_issue_date) : null} />
                <Field label="Premium" value={formatINR(details.premium_amount)} />
                <Field label="PPT (years)" value={details.ppt} />
                <Field label="PT (years)" value={details.pt} />
                <Field label="Issued At" value={details.policy_issued_at ? formatISTDateTime(details.policy_issued_at) : null} />
              </div>
            </Section>
          )}
        </div>

        <div className="space-y-6">
          {canAssign && (
            <Section title="Assignment">
              <AssignForm
                currentName={advisorDisplayName(insuranceCase.assigned_to_name, insuranceCase.assigned_to_channel)}
                onSubmit={(advisorId) => run(() => assignInsuranceCase(caseId, advisorId), "Case assigned.")}
              />
            </Section>
          )}

          {canEdit && status !== "policy_issued" && status !== "rejected" && (
            <Section title="Case Status Control">
              {status === "on_hold" ? (
                <div className="space-y-2">
                  <div className="rounded border border-border bg-background/50 px-3 py-2 text-sm">
                    <div className="text-xs text-text/50">On Hold — Reason</div>
                    <div>
                      {INSURANCE_HOLD_REASON_LABELS[insuranceCase.on_hold_reason ?? ""] ?? insuranceCase.on_hold_reason ?? "—"}
                      {insuranceCase.on_hold_other_reason && ` — ${insuranceCase.on_hold_other_reason}`}
                    </div>
                  </div>
                  <Button size="sm" className="w-full" onClick={() => run(() => resumeInsuranceCase(caseId), "Case resumed.")}>
                    Resume
                  </Button>
                </div>
              ) : (
                <HoldForm
                  onSubmit={(reason, otherReason, remarks) =>
                    run(() => holdInsuranceCase(caseId, { reason, other_reason: otherReason, remarks }), "Case placed on hold.")
                  }
                />
              )}
            </Section>
          )}

          {canReject && status !== "policy_issued" && status !== "on_hold" && (
            <Section title="Move To Stage">
              <p className="text-xs text-text/50">
                Deliberately send this case to another stage. The system still enforces every gate
                (documents verified, Premium/PPT/PT recorded).
              </p>
              <SelectField
                label="Target stage"
                name="move_target"
                value={moveTarget}
                onChange={(e) => setMoveTarget(e.target.value)}
                placeholder="Select a stage"
                options={MOVE_TO_STAGES.filter((s) => s !== status).map((s) => ({ value: s, label: STATUS_LABELS[s] ?? s }))}
              />
              <Button
                size="sm"
                className="w-full"
                disabled={!moveTarget}
                onClick={() => {
                  if (moveTarget === "rejected") {
                    setShowReject(true);
                  } else {
                    run(() => moveInsuranceCaseToStage(caseId, { target: moveTarget }), "Case moved.");
                  }
                  setMoveTarget("");
                }}
              >
                Move
              </Button>
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
                  <div className="text-xs text-text/40">{formatISTDateTime(entry.created_at)}</div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>

      {rejectingDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-card bg-card p-6 shadow-card space-y-3">
            <h3 className="text-sm font-semibold text-text">Reject {rejectingDoc.document_type_name}</h3>
            <TextareaField
              label="Reason (mandatory)"
              name="doc_reject_reason"
              value={rejectDocReason}
              onChange={(e) => setRejectDocReason(e.target.value)}
              rows={3}
              required
            />
            <div className="flex gap-2">
              <Button size="sm" variant="danger" disabled={!rejectDocReason.trim()} onClick={onRejectDoc}>
                Confirm Reject
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setRejectingDoc(null);
                  setRejectDocReason("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {showReject && (
        <RejectInsuranceCaseModal
          caseCode={insuranceCase.case_code}
          submitting={submitting}
          error={error}
          onCancel={() => setShowReject(false)}
          onConfirm={doReject}
        />
      )}

      {showPolicyLogin && (
        <PolicyLoginUpdateModal
          detail={insuranceCase}
          submitting={submitting}
          error={error}
          onCancel={() => setShowPolicyLogin(false)}
          onConfirm={doPolicyLogin}
        />
      )}

      {showPayment && (
        <PaymentUpdateModal
          detail={insuranceCase}
          submitting={submitting}
          error={error}
          onCancel={() => setShowPayment(false)}
          onConfirm={doPayment}
        />
      )}

      <ConfirmDialog
        open={confirmIssue}
        title="Move to Policy Issued"
        message="Issue this policy? Once issued, the case is closed and this cannot be undone here."
        confirmLabel="Move to Policy Issued"
        onConfirm={async () => {
          await run(() => moveToPolicyIssued(caseId), "Policy issued.");
          setConfirmIssue(false);
        }}
        onClose={() => setConfirmIssue(false)}
      />
    </SimplePageLayout>
  );
}

// Policy Leads are assigned to ACTIVE Advisors only (QR / Non QR shown for context) —
// reuses the existing Advisor master (`GET /advisors?status=active`, the same
// staff-facing endpoint the Advisors screen itself uses), never a second advisor source.
// The backend independently re-validates existence + Active status on submit, so a stale
// or manually-crafted advisor id is rejected server-side too, not just hidden here.
//
// `page_size` MUST stay at or under the API's page-size cap (100) — the previous 200
// silently 422'd on every load, which is why the dropdown always showed "No active
// advisors" even when active advisors clearly existed. Loading / success / empty / error
// are now distinct states so a future regression like that is visible, not silent.
const ADVISOR_PAGE_SIZE = 100;

function AssignForm({ currentName, onSubmit }: { currentName: string | null; onSubmit: (advisorId: string) => void }) {
  const [advisorId, setAdvisorId] = useState("");
  const [advisors, setAdvisors] = useState<AdvisorListItem[] | null>(null); // null = still loading
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setAdvisors(null);
    setLoadError(null);
    listAdvisors({ status: "active", page_size: ADVISOR_PAGE_SIZE })
      .then(({ data }) => {
        if (!cancelled) setAdvisors(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(getErrorMessage(err) || "Could not load advisors.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const loading = advisors === null && !loadError;

  return (
    <div className="space-y-2">
      {currentName && <p className="text-sm text-text/70">Currently: {currentName}</p>}

      {loading && <p className="text-sm text-text/50">Loading advisors…</p>}

      {loadError && (
        <div className="space-y-1.5 rounded border border-danger/30 bg-danger/5 px-3 py-2">
          <p className="text-xs text-danger">Could not load advisors.</p>
          <Button type="button" size="sm" variant="secondary" onClick={() => setReloadToken((t) => t + 1)}>
            Retry
          </Button>
        </div>
      )}

      {!loading && !loadError && (
        <>
          <SelectField
            label="Advisor"
            name="advisor_id"
            value={advisorId}
            onChange={(e) => setAdvisorId(e.target.value)}
            placeholder={(advisors ?? []).length ? "Select advisor" : "No active advisors"}
            options={(advisors ?? []).map((a) => ({ value: a.id, label: advisorDisplayName(a.full_name, a.channel) ?? a.full_name }))}
          />
          <Button size="sm" className="w-full" disabled={!advisorId} onClick={() => onSubmit(advisorId)}>
            {currentName ? "Reassign" : "Assign"}
          </Button>
        </>
      )}
    </div>
  );
}

function HoldForm({ onSubmit }: { onSubmit: (reason: string, otherReason: string | undefined, remarks: string | undefined) => void }) {
  const [reason, setReason] = useState(INSURANCE_HOLD_REASONS[0].value);
  const [otherReason, setOtherReason] = useState("");
  const [remarks, setRemarks] = useState("");
  const isOther = reason === "other";
  const canSubmit = !isOther || otherReason.trim().length > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit) return;
        onSubmit(reason, isOther ? otherReason.trim() : undefined, remarks || undefined);
      }}
      className="space-y-2"
    >
      <SelectField
        label="Hold Reason"
        name="hold_reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        options={INSURANCE_HOLD_REASONS.map((r) => ({ value: r.value, label: r.label }))}
      />
      {isOther && (
        <FormField
          label="Other Hold Reason"
          name="other_hold_reason"
          value={otherReason}
          onChange={(e) => setOtherReason(e.target.value)}
          required
        />
      )}
      <TextareaField label="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={2} />
      <Button type="submit" variant="secondary" size="sm" className="w-full" disabled={!canSubmit}>
        Place On Hold
      </Button>
    </form>
  );
}

// Extended applicant profile captured on "+ Add Insurance Lead" (stored in the
// application form data). Every value shows "—" when absent — old cases created before
// these fields existed simply render dashes, never fabricated data.
function ApplicantDetailsSection({ applicant }: { applicant: InsuranceApplicantDetails }) {
  return (
    <Section title="Applicant Details">
      <div className="space-y-4">
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text/40">Contact & Personal</h4>
          <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
            <Field label="Age" value={applicant.age} />
            <Field label="Profession" value={applicant.profession} />
            <Field label="Alternate Mobile" value={applicant.alternate_mobile} />
            <Field label="Education" value={applicant.education} />
            <Field label="Height (cm)" value={applicant.height} />
            <Field label="Weight (kg)" value={applicant.weight} />
            <Field label="Mother's Name" value={applicant.mother_name} />
            <Field label="Father's Name" value={applicant.father_name} />
          </div>
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text/40">Employment</h4>
          <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
            <Field label="Company Name" value={applicant.company_name} />
            <Field label="Designation" value={applicant.designation} />
            <Field label="Annual Income" value={applicant.annual_income} />
          </div>
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-text/40">Nominee</h4>
          <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
            <Field label="Nominee Name" value={applicant.nominee_name} />
            <Field label="Nominee DOB" value={applicant.nominee_dob} />
            <Field label="Relationship with Nominee" value={applicant.nominee_relationship} />
          </div>
        </div>
      </div>
    </Section>
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
