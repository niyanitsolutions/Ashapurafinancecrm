import { useState, type ReactNode } from "react";
import { groupBySection } from "@/components/forms/ProductSchemaForm";
import { FileDropZone } from "@/components/uploads/FileDropZone";
import type { ApplicationDocument, RequiredDocument } from "@/features/customer/api";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon, type IconName } from "@/theme/icons";

const STATUS_BADGE: Record<ApplicationDocument["verification_status"], { label: string; className: string; icon: IconName }> = {
  verified: { label: "Verified", className: "text-success", icon: "check-circle" },
  rejected: { label: "Rejected", className: "text-danger", icon: "x-circle" },
  pending: { label: "Pending Review", className: "text-text/50", icon: "clock" },
};

function formatFileSize(bytes: number | null): string | null {
  if (bytes == null) return null;
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function isImage(contentType: string | null): boolean {
  return Boolean(contentType?.startsWith("image/"));
}

function UploadedDocumentCard({
  doc,
  previewEnabled,
  extraActions,
}: {
  doc: ApplicationDocument;
  previewEnabled: boolean;
  extraActions?: (doc: ApplicationDocument) => ReactNode;
}) {
  const badge = STATUS_BADGE[doc.verification_status];
  const size = formatFileSize(doc.file_size_bytes);
  return (
    <div className="mt-2 flex items-start gap-3 rounded-md bg-text/5 p-2.5">
      {isImage(doc.content_type) && previewEnabled && doc.download_url ? (
        <img src={doc.download_url} alt={doc.file_name ?? "preview"} className="h-10 w-10 rounded object-cover shrink-0" />
      ) : (
        <Icon name="documents" className="h-8 w-8 shrink-0 text-text/30" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-xs text-success font-medium">
          <Icon name="check-circle" className="h-3.5 w-3.5" /> Uploaded
        </div>
        <p className="truncate text-sm text-text">{doc.file_name}</p>
        <p className="text-xs text-text/40">
          {size && `${size} · `}
          {formatISTDateTime(doc.created_at)}
        </p>
        <div className="mt-1 flex items-center gap-2 flex-wrap">
          <span className={`flex items-center gap-1 text-xs font-medium ${badge.className}`}>
            <Icon name={badge.icon} className="h-3.5 w-3.5" />
            {badge.label}
          </span>
          {doc.download_url && previewEnabled && (
            <a href={doc.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline text-xs font-medium">
              Preview
            </a>
          )}
          {doc.attachment_url && (
            <a href={doc.attachment_url} className="text-primary hover:underline text-xs font-medium">
              Download
            </a>
          )}
          {extraActions?.(doc)}
        </div>
        {doc.verification_status === "rejected" && doc.rejection_reason && (
          <p className="mt-1 text-xs text-danger">Rejected — {doc.rejection_reason}. Please re-upload this document.</p>
        )}
      </div>
    </div>
  );
}

// One upload/status slot — the entire single-document experience, parameterized on an
// optional `side` so a Front & Back document (see RequiredDocument.front_back_upload)
// renders two of these instead of forking any of this logic. `side === undefined` is
// the ordinary, single-file case — byte-for-byte the same behavior every document type
// had before Front & Back existed.
function DocumentSlot({
  typeId,
  side,
  sideLabel,
  current,
  onUpload,
  onMarkNotAvailable,
  isUploading,
  disabled,
  canMarkNotAvailable,
  isRequired,
  isMultiple,
  allowedTypes,
  maxSizeMb,
  previewEnabled,
  extraActions,
}: {
  typeId: string;
  side?: "front" | "back";
  sideLabel?: string;
  current: ApplicationDocument[];
  onUpload: (file: File) => void;
  onMarkNotAvailable?: (documentTypeId: string) => void;
  isUploading: boolean;
  disabled: boolean;
  canMarkNotAvailable: boolean;
  isRequired: boolean;
  isMultiple: boolean;
  allowedTypes?: string[] | null;
  maxSizeMb?: number | null;
  previewEnabled: boolean;
  extraActions?: (doc: ApplicationDocument) => ReactNode;
}) {
  const uploadedDocs = current.filter((d) => d.document_status === "uploaded");
  const notAvailable = uploadedDocs.length === 0 && current.some((d) => d.document_status === "not_available");
  const hasUploads = uploadedDocs.length > 0;
  const canAddMore = !disabled && (isMultiple || !hasUploads);

  return (
    <div className={side ? "mt-2 rounded-md border border-border/60 p-2.5" : undefined}>
      {sideLabel && (
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-text/60">
            {sideLabel}
            {isRequired && <span className="text-danger"> *</span>}
          </span>
          {!hasUploads && !notAvailable && <span className="text-xs font-medium text-danger">Required</span>}
        </div>
      )}

      {uploadedDocs.map((d) => (
        <UploadedDocumentCard key={d.id} doc={d} previewEnabled={previewEnabled} extraActions={extraActions} />
      ))}

      {notAvailable && (
        <div className="mt-2 flex items-center gap-1.5 rounded-md bg-text/5 px-3 py-2 text-xs text-text/50">
          <Icon name="x-circle" className="h-3.5 w-3.5" /> Not Available
        </div>
      )}

      {canAddMore && (
        <div className="mt-2">
          {isUploading ? (
            <p className="text-xs text-text/50">Uploading…</p>
          ) : hasUploads || notAvailable ? (
            <FileDropZone
              accept={allowedTypes}
              maxSizeBytes={maxSizeMb ? maxSizeMb * 1024 * 1024 : null}
              onFile={onUpload}
              compact
              compactLabel={isMultiple ? "Add Document" : "Re-upload"}
            />
          ) : (
            <FileDropZone accept={allowedTypes} maxSizeBytes={maxSizeMb ? maxSizeMb * 1024 * 1024 : null} onFile={onUpload} />
          )}
          {!isRequired && !hasUploads && !notAvailable && canMarkNotAvailable && onMarkNotAvailable && !isUploading && (
            <button
              type="button"
              onClick={() => onMarkNotAvailable(typeId)}
              className="mt-1.5 block text-xs text-text/50 hover:text-text hover:underline"
            >
              I don't have this document
            </button>
          )}
        </div>
      )}
      {notAvailable && !disabled && (
        <p className="mt-1 text-xs text-text/40">Upload it any time before submitting — it will replace this "not available" marker.</p>
      )}
    </div>
  );
}

function DocumentRow({
  doc,
  current,
  onUpload,
  onMarkNotAvailable,
  uploadingFor,
  disabled,
  canMarkNotAvailable,
  extraActions,
}: {
  doc: RequiredDocument;
  current: ApplicationDocument[];
  onUpload: (documentTypeId: string, file: File, password?: string, side?: string) => void;
  onMarkNotAvailable?: (documentTypeId: string) => void;
  uploadingFor: string | null;
  disabled: boolean;
  canMarkNotAvailable: boolean;
  extraActions?: (doc: ApplicationDocument) => ReactNode;
}) {
  // Bank Statement password — local, component-only state (never lifted to a parent
  // store, never persisted to localStorage/sessionStorage): the value is read once at
  // upload time and handed straight to `onUpload`, which forwards it to the confirm
  // API call and clears it from this component the moment the field re-renders empty
  // after a successful upload (React remounts a fresh empty input; nothing to clear
  // manually). Only rendered at all when `doc.supports_password` — see
  // RequiredDocument's own docstring on where that flag comes from. Shown once per row
  // (not per Front/Back side) — a password protects the document as a whole.
  const [password, setPassword] = useState("");
  const typeId = doc.document_type_id;
  const isRequired = doc.required !== false;
  const isMultiple = doc.multiple_upload === true;
  const previewEnabled = doc.preview_enabled !== false;
  const isUploading = uploadingFor === typeId;
  const isFrontBack = doc.front_back_upload === true;
  const displayName = current[0]?.document_type_name || doc.name_override || doc.document_type_name || "Document";
  // Front & Back has no "not available" concept server-side (see CustomerService.
  // mark_document_not_available's own rejection of this combination) — the two-sided
  // UI never offers the action.
  const effectiveCanMarkNotAvailable = canMarkNotAvailable && !isFrontBack;

  const makeUpload = (side?: "front" | "back") => (file: File) => {
    onUpload(typeId, file, doc.supports_password ? password || undefined : undefined, side);
    setPassword("");
  };

  const passwordField = doc.supports_password && (
    <div className="mb-2">
      <label className="mb-1 block text-xs font-medium text-text/60" htmlFor={`doc-password-${typeId}`}>
        Bank Statement Password (if applicable)
      </label>
      <input
        id={`doc-password-${typeId}`}
        type="password"
        autoComplete="off"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Enter statement password"
        className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
      <p className="mt-1 text-2xs text-text/40">
        Enter the password only if your bank statement is password protected. Leave this blank if the statement is not password protected.
      </p>
    </div>
  );

  return (
    <li className="text-sm rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-text">
          {displayName}
          {isRequired ? <span className="text-danger"> *</span> : <span className="font-normal text-text/40"> (Optional)</span>}
          {doc.note && <span className="font-normal text-text/40"> — {doc.note}</span>}
        </span>
      </div>

      {passwordField}

      {isFrontBack ? (
        <>
          <DocumentSlot
            typeId={typeId}
            side="front"
            sideLabel="Front Side"
            current={current.filter((d) => d.side === "front")}
            onUpload={makeUpload("front")}
            isUploading={isUploading}
            disabled={disabled}
            canMarkNotAvailable={false}
            isRequired={isRequired}
            isMultiple={false}
            allowedTypes={doc.allowed_types}
            maxSizeMb={doc.max_size_mb}
            previewEnabled={previewEnabled}
            extraActions={extraActions}
          />
          <DocumentSlot
            typeId={typeId}
            side="back"
            sideLabel="Back Side"
            current={current.filter((d) => d.side === "back")}
            onUpload={makeUpload("back")}
            isUploading={isUploading}
            disabled={disabled}
            canMarkNotAvailable={false}
            isRequired={isRequired}
            isMultiple={false}
            allowedTypes={doc.allowed_types}
            maxSizeMb={doc.max_size_mb}
            previewEnabled={previewEnabled}
            extraActions={extraActions}
          />
        </>
      ) : (
        <DocumentSlot
          typeId={typeId}
          current={current}
          onUpload={makeUpload(undefined)}
          onMarkNotAvailable={onMarkNotAvailable}
          isUploading={isUploading}
          disabled={disabled}
          canMarkNotAvailable={effectiveCanMarkNotAvailable}
          isRequired={isRequired}
          isMultiple={isMultiple}
          allowedTypes={doc.allowed_types}
          maxSizeMb={doc.max_size_mb}
          previewEnabled={previewEnabled}
          extraActions={extraActions}
        />
      )}
    </li>
  );
}

// Phase 5 (status badges added in the Customer Portal redesign) — extracted from
// ApplicationPage (Phase 3.1) so the Application form's own Documents step, the Customer
// Portal's dedicated Document Center, and (Document Management redesign) the
// Employee/Owner Staff Application view all render the exact same grouped checklist, off
// the exact same Product Schema data and the exact same document records — one
// component, not several copies of the same business logic per role.
export function DocumentChecklist({
  requiredDocuments,
  uploadedDocuments,
  onUpload,
  onMarkNotAvailable,
  uploadingFor,
  disabled = false,
  canMarkNotAvailable = false,
  extraActions,
}: {
  requiredDocuments: RequiredDocument[];
  uploadedDocuments: ApplicationDocument[];
  onUpload: (documentTypeId: string, file: File, password?: string, side?: string) => void;
  onMarkNotAvailable?: (documentTypeId: string) => void;
  uploadingFor: string | null;
  disabled?: boolean;
  // Section 6 ("I don't have this document") is Customer-only — staff never waive a
  // document on someone else's behalf (the backend endpoint is Customer-only too); this
  // just keeps the Staff view from offering an action the backend would reject anyway.
  canMarkNotAvailable?: boolean;
  // Staff-only extras (Verify/Reject) rendered next to a specific uploaded document,
  // without forking this component for the Staff Application page.
  extraActions?: (doc: ApplicationDocument) => ReactNode;
}) {
  // Governance round — a `hidden` required-document entry (Owner-set, see
  // SchemaEditorPage) is never shown, same as a hidden field never renders.
  const visibleDocuments = requiredDocuments.filter((d) => !d.hidden);

  return (
    <>
      {groupBySection(visibleDocuments).map(([sectionName, docs], groupIndex) => (
        <div key={sectionName ?? "_default"} className={groupIndex > 0 ? "mt-4 pt-4 border-t border-border" : ""}>
          {sectionName && <h3 className="text-xs font-semibold text-text/50 uppercase tracking-wide mb-2">{sectionName}</h3>}
          <ul className="space-y-2.5">
            {docs.map((doc) => (
              <DocumentRow
                key={doc.document_type_id}
                doc={doc}
                current={uploadedDocuments.filter((d) => d.document_type_id === doc.document_type_id && d.is_current)}
                onUpload={onUpload}
                onMarkNotAvailable={onMarkNotAvailable}
                uploadingFor={uploadingFor}
                disabled={disabled}
                canMarkNotAvailable={canMarkNotAvailable}
                extraActions={extraActions}
              />
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

/** "3 / 5 required documents completed" + the list of what's still missing — spec §7/§8.
 * Derived purely from schema + current documents already in scope at every call site, no
 * extra API call. A Front & Back requirement (RequiredDocument.front_back_upload) only
 * counts as completed once BOTH sides have a current upload. */
export function documentCompletionSummary(requiredDocuments: RequiredDocument[], uploadedDocuments: ApplicationDocument[]) {
  const required = requiredDocuments.filter((d) => !d.hidden && d.required !== false);
  const current = uploadedDocuments.filter((d) => d.is_current && d.document_status === "uploaded");
  const isSatisfied = (d: RequiredDocument) => {
    const docs = current.filter((u) => u.document_type_id === d.document_type_id);
    if (d.front_back_upload) {
      return docs.some((u) => u.side === "front") && docs.some((u) => u.side === "back");
    }
    return docs.length > 0;
  };
  const missing = required.filter((d) => !isSatisfied(d));
  return { total: required.length, completed: required.length - missing.length, missing };
}
