import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addOtherDocument,
  getOtherDocumentHistory,
  listOtherDocuments,
  rejectOtherDocument,
  uploadOtherDocument,
  verifyOtherDocument,
  type OtherDocument,
} from "@/features/insurance_management/api";
import { formatISTDateTime } from "@/shared/dateFormat";

const STATUS_LABELS: Record<string, string> = { pending: "Uploaded — Pending Review", verified: "Verified", rejected: "Rejected" };

// "Add Other Document" — staff names a document (free text), then uploads a file against
// it here (or the customer uploads from their portal). Ad-hoc and per-case: it NEVER
// touches the Product Schema / global Document Types, and an unverified Other Document
// does NOT block moving the case forward. A rejected document can be re-uploaded; the old
// version is kept in history (backend supersede), never overwritten or deleted.
export function AddOtherDocumentPanel({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const [documents, setDocuments] = useState<OtherDocument[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<OtherDocument[]>([]);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = () => {
    listOtherDocuments(caseId)
      .then(setDocuments)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [caseId]);

  const handleAdd = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      await addOtherDocument(caseId, name.trim());
      setName("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleUpload = async (docId: string, file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusyId(docId);
    try {
      await uploadOtherDocument(caseId, docId, file);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleVerify = async (docId: string) => {
    setError(null);
    try {
      await verifyOtherDocument(caseId, docId);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleReject = async (docId: string) => {
    if (!rejectReason.trim()) return;
    setError(null);
    try {
      await rejectOtherDocument(caseId, docId, rejectReason.trim());
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const toggleHistory = async (docId: string) => {
    if (historyFor === docId) {
      setHistoryFor(null);
      return;
    }
    try {
      setHistory(await getOtherDocumentHistory(caseId, docId));
      setHistoryFor(docId);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const uploadButton = (doc: OtherDocument, label: string) => (
    <>
      <input
        ref={(el) => {
          fileInputs.current[doc.id] = el;
        }}
        type="file"
        className="hidden"
        onChange={(e) => handleUpload(doc.id, e.target.files?.[0])}
      />
      <Button size="sm" loading={busyId === doc.id} onClick={() => fileInputs.current[doc.id]?.click()}>
        {label}
      </Button>
    </>
  );

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-danger">{error}</p>}

      {canEdit && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <FormField
              label="Document Name"
              name="other_document_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Medical Prescription"
            />
          </div>
          <Button size="sm" disabled={!name.trim()} onClick={handleAdd}>
            + Add Document
          </Button>
        </div>
      )}

      {documents.length === 0 && <p className="text-sm text-text/40">No other documents added yet.</p>}

      {documents.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-text/50">Other Documents</h4>
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

              {doc.file_name && <p className="text-xs text-text/60">{doc.file_name}</p>}
              {doc.verification_status === "rejected" && doc.rejection_reason && (
                <p className="text-xs text-danger">Reason: {doc.rejection_reason}</p>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {canEdit && doc.document_status === "requested" && uploadButton(doc, "Upload")}
                {canEdit && doc.document_status === "uploaded" && doc.verification_status === "rejected" && uploadButton(doc, "Re-upload")}

                {doc.document_status === "uploaded" && doc.download_url && (
                  <a href={doc.download_url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="secondary" type="button">
                      Preview
                    </Button>
                  </a>
                )}
                {doc.document_status === "uploaded" && doc.attachment_url && (
                  <a href={doc.attachment_url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="secondary" type="button">
                      Download
                    </Button>
                  </a>
                )}
                {canEdit && doc.document_status === "uploaded" && doc.verification_status === "pending" && (
                  <>
                    <Button size="sm" onClick={() => handleVerify(doc.id)}>
                      Verify
                    </Button>
                    {rejectingId !== doc.id && (
                      <Button size="sm" variant="danger" onClick={() => setRejectingId(doc.id)}>
                        Reject
                      </Button>
                    )}
                  </>
                )}
                {doc.doc_version > 1 && (
                  <button type="button" className="text-2xs text-primary hover:underline" onClick={() => toggleHistory(doc.id)}>
                    {historyFor === doc.id ? "Hide history" : `History (v${doc.doc_version})`}
                  </button>
                )}
              </div>

              {historyFor === doc.id && (
                <ul className="mt-1 space-y-0.5 border-t border-border pt-1 text-2xs text-text/60">
                  {history.map((v) => (
                    <li key={v.id} className="flex items-center gap-2">
                      <span>v{v.doc_version}</span>
                      <span>{v.file_name ?? "—"}</span>
                      <span>{v.verification_status}</span>
                      {v.uploaded_at && <span>{formatISTDateTime(v.uploaded_at)}</span>}
                      {v.download_url && (
                        <a href={v.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                          Preview
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {rejectingId === doc.id && (
                <div className="space-y-2 rounded border border-danger/30 bg-danger/5 px-3 py-2">
                  <TextareaField
                    label="Reason (mandatory)"
                    name="other_document_rejection_reason"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    rows={2}
                    required
                  />
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
