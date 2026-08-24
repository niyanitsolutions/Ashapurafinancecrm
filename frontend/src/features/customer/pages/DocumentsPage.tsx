import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { DocumentChecklist } from "@/features/customer/components/DocumentChecklist";
import {
  getFormDefinition,
  listDocuments,
  listOwnApplications,
  markDocumentNotAvailable,
  uploadApplicationDocument,
  type ApplicationDocument,
  type ApplicationListItem,
  type FormDefinition,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon } from "@/theme/icons";

interface ApplicationDocs {
  application: ApplicationListItem;
  formDef: FormDefinition;
  documents: ApplicationDocument[];
}

// Phase 5 — Document Center: every application's required documents, grouped by
// section, in one place — reuses the exact same `DocumentChecklist` component (and the
// exact same upload flow) the Application form itself uses, so there's only one place
// this logic is implemented.
export function DocumentsPage() {
  const [groups, setGroups] = useState<ApplicationDocs[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);

  const load = async () => {
    try {
      const applications = await listOwnApplications();
      const withDocs = await Promise.all(
        applications.map(async (application) => {
          const [formDef, documents] = await Promise.all([
            getFormDefinition(application.product_category, application.product_id),
            listDocuments(application.id),
          ]);
          return { application, formDef, documents };
        }),
      );
      setGroups(withDocs);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onUpload = async (applicationId: string, documentTypeId: string, file: File, password?: string, side?: string) => {
    setError(null);
    setUploadingFor(documentTypeId);
    try {
      await uploadApplicationDocument(applicationId, documentTypeId, file, password, side);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploadingFor(null);
    }
  };

  const onMarkNotAvailable = async (applicationId: string, documentTypeId: string) => {
    setError(null);
    try {
      await markDocumentNotAvailable(applicationId, documentTypeId);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Document Center" backTo="/portal">
      <ErrorBanner message={error} />
      {error && (
        <button type="button" onClick={load} className="mb-4 text-sm font-medium text-primary hover:underline">
          Try Again
        </button>
      )}

      {groups === null && !error && (
        <div className="max-w-2xl space-y-4">
          {[0, 1].map((i) => (
            <div key={i} className="animate-shimmer h-32 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
          ))}
        </div>
      )}

      {groups !== null && groups.length === 0 && (
        <div className="bg-card border border-border rounded-card shadow-card p-10 text-center max-w-2xl">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Icon name="documents" className="h-6 w-6" />
          </span>
          <p className="text-sm font-medium text-text mb-1">No Documents Yet</p>
          <p className="text-sm text-text/50">Start an application to see its required documents here.</p>
        </div>
      )}

      {groups?.map(({ application, formDef, documents }) => (
        <div key={application.id} className="bg-card border border-border rounded-card shadow-card p-6 mb-6 max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text">{application.product_name}</h2>
            <span className="text-xs text-text/50">{application.application_code}</span>
          </div>
          <DocumentChecklist
            requiredDocuments={formDef.required_documents}
            uploadedDocuments={documents}
            onUpload={(documentTypeId, file, password, side) => onUpload(application.id, documentTypeId, file, password, side)}
            onMarkNotAvailable={(documentTypeId) => onMarkNotAvailable(application.id, documentTypeId)}
            canMarkNotAvailable={application.status !== "submitted"}
            uploadingFor={uploadingFor}
            // Deliberately NOT disabled once submitted: `confirm_document` (the actual
            // backend upload endpoint) has no submission-status gate at all — re-upload
            // after submission is exactly how the reject/re-upload lifecycle is meant to
            // work, since staff review (and therefore rejection) only ever happens AFTER
            // submission. Blanket-disabling here used to make a rejected document's
            // "Re-upload" control unreachable from this page — the Staff Portal's own
            // equivalent page never disabled DocumentChecklist at all, so this was a
            // real Customer-Portal-only regression, not a deliberate restriction.
            // `DocumentSlot`'s own per-document gate (`canAddMore`) already correctly
            // blocks touching a document that's pending/verified and not eligible for
            // re-upload; only a genuinely rejected (or not-yet-uploaded, or
            // multiple-upload) document ever exposes an upload control here.
          />
        </div>
      ))}
    </SimplePageLayout>
  );
}
