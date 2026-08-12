import { groupBySection } from "@/components/forms/ProductSchemaForm";
import type { ApplicationDocument, RequiredDocument } from "@/features/customer/api";
import { Icon, type IconName } from "@/theme/icons";

const STATUS_BADGE: Record<ApplicationDocument["verification_status"], { label: string; className: string; icon: IconName }> = {
  verified: { label: "Verified", className: "text-success", icon: "check-circle" },
  rejected: { label: "Rejected", className: "text-danger", icon: "x-circle" },
  pending: { label: "Pending Review", className: "text-text/50", icon: "clock" },
};

// Phase 5 (status badges added in the Customer Portal redesign) — extracted from
// ApplicationPage (Phase 3.1) so the Application form's own Documents step and the
// Customer Portal's dedicated Document Center render the exact same grouped checklist,
// with the exact same upload behavior and the same real verification status per file —
// one component, not two copies of the same business logic.
export function DocumentChecklist({
  requiredDocuments,
  uploadedDocuments,
  onUpload,
  uploadingFor,
  disabled = false,
}: {
  requiredDocuments: RequiredDocument[];
  uploadedDocuments: ApplicationDocument[];
  onUpload: (documentTypeId: string, file: File) => void;
  uploadingFor: string | null;
  disabled?: boolean;
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
            {docs.map((doc) => {
              const typeId = doc.document_type_id;
              const uploaded = uploadedDocuments.filter((d) => d.document_type_id === typeId);
              const isUploaded = uploaded.length > 0;
              const latest = uploaded[0];
              const badge = latest ? STATUS_BADGE[latest.verification_status] : null;
              const displayName = latest?.document_type_name || doc.name_override || doc.document_type_name || "Document";
              const accept = doc.allowed_types?.length ? doc.allowed_types.map((t) => `.${t.replace(/^\./, "")}`).join(",") : undefined;
              return (
                <li key={typeId} className="text-sm rounded-lg border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className={isUploaded ? "text-text" : "text-text/70"}>
                      <Icon name={isUploaded ? "check-circle" : "clock"} className={`inline h-4 w-4 mr-1.5 -mt-0.5 ${isUploaded ? "text-success" : "text-text/30"}`} />
                      {displayName}
                      {doc.required === false && <span className="text-text/40"> (Optional)</span>}
                      {doc.note && <span className="text-text/40"> ({doc.note})</span>}
                      {doc.max_size_mb != null && <span className="text-text/30"> · max {doc.max_size_mb}MB</span>}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      {badge && (
                        <span className={`flex items-center gap-1 text-xs font-medium ${badge.className}`}>
                          <Icon name={badge.icon} className="h-3.5 w-3.5" />
                          {badge.label}
                        </span>
                      )}
                      {!disabled && (
                        <label className="text-primary hover:underline cursor-pointer text-xs font-medium">
                          {uploadingFor === typeId ? "Uploading…" : isUploaded ? "Replace" : "Upload"}
                          <input
                            type="file"
                            className="hidden"
                            accept={accept}
                            disabled={uploadingFor === typeId}
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) onUpload(typeId, file);
                            }}
                          />
                        </label>
                      )}
                    </div>
                  </div>
                  {latest?.verification_status === "rejected" && latest.rejection_reason && (
                    <p className="mt-1.5 text-xs text-danger">Rejected — {latest.rejection_reason}. Please re-upload this document.</p>
                  )}
                  {uploaded.map((d) => (
                    <div key={d.id} className="text-xs text-text/50 pl-5 mt-1">
                      {d.download_url ? (
                        <a href={d.download_url} target="_blank" rel="noreferrer" className="hover:underline">
                          {d.file_name}
                        </a>
                      ) : (
                        d.file_name
                      )}
                    </div>
                  ))}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </>
  );
}
