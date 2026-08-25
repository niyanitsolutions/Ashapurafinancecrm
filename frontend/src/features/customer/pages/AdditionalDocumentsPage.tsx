import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  listOwnAdditionalDocuments,
  listOwnLoanCases,
  uploadOwnAdditionalDocument,
  type AdditionalDocument,
  type LoanCaseListItem,
} from "@/features/loan_management/api";

const STATUS_LABELS: Record<string, string> = { pending: "Under Review", verified: "Verified", rejected: "Rejected" };

// Customer-facing Additional Documents (requirement 13-14, 17): shows EXACTLY the
// document name staff requested — never a generic "Document 1" placeholder — with an
// upload control per document, and the rejection reason when applicable.
export function AdditionalDocumentsPage() {
  const { id: applicationId } = useParams<{ id: string }>();
  const [loanCase, setLoanCase] = useState<LoanCaseListItem | null>(null);
  const [documents, setDocuments] = useState<AdditionalDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = () => {
    if (!applicationId) return;
    setError(null);
    listOwnLoanCases()
      .then(async (cases) => {
        const match = cases.find((c) => c.application_id === applicationId);
        if (!match) {
          setError("No loan case exists yet for this application.");
          setIsLoading(false);
          return;
        }
        setLoanCase(match);
        const docs = await listOwnAdditionalDocuments(match.id);
        setDocuments(docs);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [applicationId]);

  const handleUpload = async (docId: string, file: File) => {
    if (!loanCase) return;
    setError(null);
    setUploadingId(docId);
    try {
      await uploadOwnAdditionalDocument(loanCase.id, docId, file);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploadingId(null);
    }
  };

  return (
    <SimplePageLayout title="Additional Documents" backTo={applicationId ? `/portal/applications/${applicationId}/timeline` : "/portal"}>
      <ErrorBanner message={error} />

      {isLoading && <p className="text-sm text-text/40">Loading…</p>}

      {!isLoading && documents.length === 0 && <p className="text-sm text-text/40">No additional documents have been requested.</p>}

      <div className="space-y-3">
        {documents.map((doc) => (
          <div key={doc.id} className="rounded-card border border-border bg-card shadow-card p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-text">{doc.name}</h3>
              {doc.document_status === "uploaded" && (
                <span
                  className={`rounded-full px-2 py-0.5 text-2xs font-semibold ${
                    doc.verification_status === "verified"
                      ? "bg-success/10 text-success"
                      : doc.verification_status === "rejected"
                        ? "bg-danger/10 text-danger"
                        : "bg-warning/10 text-warning"
                  }`}
                >
                  {STATUS_LABELS[doc.verification_status]}
                </span>
              )}
            </div>

            {doc.verification_status === "rejected" && doc.rejection_reason && (
              <div className="mt-2 rounded border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                <p className="font-medium">Reason: {doc.rejection_reason}</p>
                <p className="mt-1 text-xs">Please upload a new document.</p>
              </div>
            )}

            {(doc.document_status === "requested" || doc.verification_status === "rejected") && (
              <div className="mt-3">
                <input
                  ref={(el) => {
                    fileInputs.current[doc.id] = el;
                  }}
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void handleUpload(doc.id, file);
                    e.target.value = "";
                  }}
                />
                <Button size="sm" loading={uploadingId === doc.id} onClick={() => fileInputs.current[doc.id]?.click()}>
                  {doc.verification_status === "rejected" ? "Re-upload" : "Upload Document"}
                </Button>
              </div>
            )}

            {doc.document_status === "uploaded" && doc.verification_status !== "rejected" && doc.file_name && (
              <p className="mt-2 text-sm text-text/60">Uploaded: {doc.file_name}</p>
            )}
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}
