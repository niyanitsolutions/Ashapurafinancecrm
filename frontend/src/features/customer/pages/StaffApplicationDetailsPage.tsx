import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Icon } from "@/theme/icons";
import { useAuth } from "@/features/auth/useAuth";
import {
  assignApplication,
  getApplication,
  listDocuments,
  rejectDocument,
  verifyDocument,
  type ApplicationDetail,
  type ApplicationDocument,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

const STATUS_BADGE: Record<ApplicationDocument["verification_status"], { label: string; className: string; icon: "check-circle" | "x-circle" | "clock" }> = {
  verified: { label: "Verified", className: "text-success", icon: "check-circle" },
  rejected: { label: "Rejected", className: "text-danger", icon: "x-circle" },
  pending: { label: "Pending Review", className: "text-text/50", icon: "clock" },
};

function RejectDocumentModal({
  fileName,
  onClose,
  onConfirm,
}: {
  fileName: string;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) return;
    setIsSubmitting(true);
    await onConfirm(reason.trim());
    setIsSubmitting(false);
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Reject Document"
      description={fileName}
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" type="submit" form="reject-document-form" size="sm" loading={isSubmitting} disabled={!reason.trim()}>
            Confirm Reject
          </Button>
        </>
      }
    >
      <form id="reject-document-form" onSubmit={onSubmit}>
        <FormField label="Rejection reason" value={reason} onChange={(e) => setReason(e.target.value)} required autoFocus />
      </form>
    </Modal>
  );
}

export function StaffApplicationDetailsPage() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const { role } = useAuth();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [rejectingDoc, setRejectingDoc] = useState<ApplicationDocument | null>(null);

  const load = () => {
    if (!applicationId) return;
    getApplication(applicationId)
      .then(setApplication)
      .catch((err) => setError(getErrorMessage(err)));
    listDocuments(applicationId)
      .then(setDocuments)
      .catch(() => setDocuments([]));
  };

  useEffect(load, [applicationId]);

  if (!applicationId) return null;
  if (error && !application) {
    return (
      <SimplePageLayout title="Application" backTo="/applications">
        <p className="text-sm text-danger">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!application) {
    return (
      <SimplePageLayout title="Application" backTo="/applications">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  const onAssign = async () => {
    setError(null);
    setMessage(null);
    try {
      await assignApplication(applicationId, employeeId);
      setMessage("Application assigned.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onVerify = async (documentId: string) => {
    setError(null);
    setMessage(null);
    try {
      await verifyDocument(applicationId, documentId);
      setMessage("Document verified.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onReject = async (documentId: string, reason: string) => {
    setError(null);
    setMessage(null);
    try {
      await rejectDocument(applicationId, documentId, reason);
      setMessage("Document rejected.");
      setRejectingDoc(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title={application.application_code} backTo="/applications">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Details</h2>
            <p className="text-sm text-text/60 mb-2 capitalize">
              {application.product_name} · {application.status}
            </p>
            <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              {Object.entries(application.form_data).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-xs text-text/50 capitalize">{key.replace(/_/g, " ")}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Documents</h2>
            {documents.length === 0 && (
              <p className="text-sm text-text/50">No documents uploaded yet.</p>
            )}
            <ul className="space-y-3">
              {documents.map((d) => {
                const badge = STATUS_BADGE[d.verification_status];
                return (
                  <li key={d.id} className="border border-border rounded-lg p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <span className="text-text/70">{d.document_type_name}: </span>
                        {d.download_url ? (
                          <a href={d.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                            {d.file_name}
                          </a>
                        ) : (
                          d.file_name
                        )}
                      </div>
                      <span className={`flex items-center gap-1 text-xs font-medium ${badge.className}`}>
                        <Icon name={badge.icon} className="h-4 w-4" />
                        {badge.label}
                      </span>
                    </div>
                    {d.verification_status === "rejected" && d.rejection_reason && (
                      <p className="mt-1 text-xs text-danger">Reason: {d.rejection_reason}</p>
                    )}
                    {d.verification_status === "pending" && (
                      <div className="mt-2 flex items-center gap-2">
                        <Button variant="secondary" size="sm" onClick={() => onVerify(d.id)}>
                          Verify
                        </Button>
                        <Button variant="danger" size="sm" onClick={() => setRejectingDoc(d)}>
                          Reject
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3">
          <h3 className="text-sm font-semibold text-text/70">Assignment</h3>
          <p className="text-sm text-text">{application.assigned_to_name || "Unassigned"}</p>
          {role === "owner" && (
            <>
              <EmployeeSelect label="Assign to" value={employeeId} onChange={setEmployeeId} />
              <Button size="sm" className="w-full" disabled={!employeeId} onClick={onAssign}>
                Assign
              </Button>
            </>
          )}
        </div>
      </div>

      {rejectingDoc && (
        <RejectDocumentModal
          fileName={rejectingDoc.file_name}
          onClose={() => setRejectingDoc(null)}
          onConfirm={(reason) => onReject(rejectingDoc.id, reason)}
        />
      )}
    </SimplePageLayout>
  );
}
