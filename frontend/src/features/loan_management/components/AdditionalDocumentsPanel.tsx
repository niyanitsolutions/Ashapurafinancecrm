import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addAdditionalDocument,
  listAdditionalDocuments,
  rejectAdditionalDocument,
  verifyAdditionalDocument,
  type AdditionalDocument,
} from "@/features/loan_management/api";

const STATUS_LABELS: Record<string, string> = { pending: "Uploaded — Pending Review", verified: "Verified", rejected: "Rejected" };

// Additional Documents — staff requests a document by NAME (free text), not a fixed
// checklist (requirement 12). The customer sees exactly this name and uploads against
// it; once uploaded, staff Preview/Download/Verify/Reject here.
export function AdditionalDocumentsPanel({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const [documents, setDocuments] = useState<AdditionalDocument[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = () => {
    listAdditionalDocuments(caseId)
      .then(setDocuments)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [caseId]);

  const handleAdd = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      await addAdditionalDocument(caseId, name.trim());
      setName("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleVerify = async (docId: string) => {
    setError(null);
    try {
      await verifyAdditionalDocument(caseId, docId);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleReject = async (docId: string) => {
    if (!rejectReason.trim()) return;
    setError(null);
    try {
      await rejectAdditionalDocument(caseId, docId, rejectReason.trim());
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-danger">{error}</p>}

      {canEdit && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <FormField label="Document Name" name="additional_document_name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Salary Revision Letter" />
          </div>
          <Button size="sm" disabled={!name.trim()} onClick={handleAdd}>
            + Add Document
          </Button>
        </div>
      )}

      {documents.length === 0 && <p className="text-sm text-text/40">No additional documents requested yet.</p>}

      {documents.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-text/50">Requested Documents</h4>
          {documents.map((doc) => (
            <div key={doc.id} className="rounded border border-border p-3 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium text-text">{doc.name}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-2xs font-semibold ${
                    doc.document_status === "requested"
                      ? "bg-text/10 text-text/60"
                      : doc.verification_status === "verified"
                        ? "bg-success/10 text-success"
                        : doc.verification_status === "rejected"
                          ? "bg-danger/10 text-danger"
                          : "bg-warning/10 text-warning"
                  }`}
                >
                  {doc.document_status === "requested" ? "Pending Upload" : STATUS_LABELS[doc.verification_status]}
                </span>
              </div>
              {doc.verification_status === "rejected" && doc.rejection_reason && (
                <p className="text-xs text-danger">Reason: {doc.rejection_reason}</p>
              )}
              {doc.document_status === "uploaded" && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {doc.download_url && (
                    <a href={doc.download_url} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="secondary" type="button">
                        Preview
                      </Button>
                    </a>
                  )}
                  {doc.attachment_url && (
                    <a href={doc.attachment_url} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="secondary" type="button">
                        Download
                      </Button>
                    </a>
                  )}
                  {canEdit && doc.verification_status !== "verified" && (
                    <Button size="sm" onClick={() => handleVerify(doc.id)}>
                      Verify
                    </Button>
                  )}
                  {canEdit && doc.verification_status !== "rejected" && rejectingId !== doc.id && (
                    <Button size="sm" variant="danger" onClick={() => setRejectingId(doc.id)}>
                      Reject
                    </Button>
                  )}
                </div>
              )}
              {rejectingId === doc.id && (
                <div className="space-y-2 rounded border border-danger/30 bg-danger/5 px-3 py-2">
                  <TextareaField label="Reason (mandatory)" name="rejection_reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={2} required />
                  <div className="flex gap-2">
                    <Button size="sm" variant="danger" disabled={!rejectReason.trim()} onClick={() => handleReject(doc.id)}>
                      Confirm Reject
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setRejectingId(null);
                        setRejectReason("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
