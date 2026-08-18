import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { useAuth } from "@/features/auth/useAuth";
import { DocumentChecklist } from "@/features/customer/components/DocumentChecklist";
import {
  assignApplication,
  confirmDocument,
  getApplication,
  getDocumentUploadUrl,
  listDocuments,
  rejectDocument,
  verifyDocument,
  type ApplicationDetail,
  type ApplicationDocument,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { useProductSchema } from "@/features/customer/useProductSchema";

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
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);

  // Document Management redesign — the Staff Application view now reads the exact same
  // Product Schema (`required_documents`) and renders it through the exact same
  // `DocumentChecklist` component the Customer Portal uses, so Employee/Owner see missing
  // required documents too, not only the ones already uploaded — and Customer/Employee/
  // Owner are guaranteed to be looking at the same document records, never a separate
  // staff-only rendering of them.
  const { data: formDef } = useProductSchema(application?.product_category, application?.product_id);

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

  const onUploadDocument = async (documentTypeId: string, file: File) => {
    setError(null);
    setUploadingFor(documentTypeId);
    try {
      const { upload_url, s3_key } = await getDocumentUploadUrl(applicationId, documentTypeId, file.name, file.type);
      await fetch(upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      await confirmDocument(applicationId, documentTypeId, file.name, s3_key, file.type);
      setMessage("Document uploaded.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploadingFor(null);
    }
  };

  const documentExtraActions = (doc: ApplicationDocument) => (
    <>
      {doc.download_url && (
        <a href={doc.download_url} download={doc.file_name ?? undefined} className="text-primary hover:underline text-xs font-medium">
          Download
        </a>
      )}
      {doc.verification_status === "pending" && (
        <>
          <button type="button" onClick={() => onVerify(doc.id)} className="text-xs font-medium text-success hover:underline">
            Verify
          </button>
          <button type="button" onClick={() => setRejectingDoc(doc)} className="text-xs font-medium text-danger hover:underline">
            Reject
          </button>
        </>
      )}
    </>
  );

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
            {formDef ? (
              <DocumentChecklist
                requiredDocuments={formDef.required_documents}
                uploadedDocuments={documents}
                onUpload={onUploadDocument}
                uploadingFor={uploadingFor}
                extraActions={documentExtraActions}
              />
            ) : (
              <p className="text-sm text-text/50">Loading…</p>
            )}
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
          fileName={rejectingDoc.file_name ?? rejectingDoc.document_type_name}
          onClose={() => setRejectingDoc(null)}
          onConfirm={(reason) => onReject(rejectingDoc.id, reason)}
        />
      )}
    </SimplePageLayout>
  );
}
