import { useState, type ComponentProps } from "react";
import { DocumentChecklist } from "./DocumentChecklist";
import { getDocumentHistory, type ApplicationDocument } from "../api";
import { getErrorMessage } from "../errors";
import { formatISTDateTime } from "@/shared/dateFormat";

export function CustomerDocumentChecklist({ applicationId, progress, ...props }: ComponentProps<typeof DocumentChecklist> & {
  applicationId: string; progress?: number | null;
}) {
  const [history, setHistory] = useState<{ name: string; rows: ApplicationDocument[] } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  return <div>
    {props.uploadingFor && <div role="status" aria-live="polite" className="portal-card mb-4">
      <p>Uploading your document{progress != null ? ` · ${progress}%` : "…"}. Please keep this page open.</p>
      <progress aria-label="Document upload progress" value={progress ?? undefined} max={100} className="w-full" />
    </div>}
    <DocumentChecklist {...props} />
    <div className="mt-5 grid gap-3">
      {props.requiredDocuments.filter(doc => !doc.hidden).map(doc => <div className="flex flex-wrap items-center gap-3" key={doc.document_type_id}>
        {props.uploadedDocuments.some(upload => upload.document_type_id === doc.document_type_id) && <button
          type="button" disabled={loading === doc.document_type_id} className="text-sm text-primary"
          onClick={async () => {
            setLoading(doc.document_type_id); setError(null);
            try { setHistory({ name: doc.name_override || doc.document_type_name, rows: await getDocumentHistory(applicationId, doc.document_type_id) }); }
            catch (e) { setError(getErrorMessage(e)); } finally { setLoading(null); }
          }}>{loading === doc.document_type_id ? "Loading history…" : `${doc.name_override || doc.document_type_name} · version history`}</button>}
        {!props.disabled && !doc.front_back_upload && !doc.front_back_optional && !doc.supports_password &&
          (doc.multiple_upload || !props.uploadedDocuments.some(row => row.document_type_id === doc.document_type_id && row.is_current && row.document_status === "uploaded") ||
            props.uploadedDocuments.some(row => row.document_type_id === doc.document_type_id && row.is_current && row.verification_status === "rejected")) &&
          (!doc.allowed_types?.length || doc.allowed_types.some(type => /image|jpg|jpeg|png/i.test(type))) &&
          <label className="portal-camera text-sm text-primary min-h-11 items-center gap-2 cursor-pointer border rounded-lg px-3">Take a photo of {doc.name_override || doc.document_type_name}
            <input type="file" accept="image/*" capture="environment" disabled={!!props.uploadingFor}
              className="sr-only" aria-label={`Camera upload ${doc.document_type_name}`} onChange={event => {
                const file = event.target.files?.[0];
                if (file && doc.max_size_mb && file.size > doc.max_size_mb * 1024 * 1024) setError(`Choose a file smaller than ${doc.max_size_mb} MB.`);
                else if (file) void props.onUpload(doc.document_type_id, file);
                event.target.value = "";
              }} />
          </label>}
      </div>)}
    </div>
    {error && <p role="alert" className="mt-3 text-danger">{error}</p>}
    {history && <section className="portal-card mt-4" aria-label={`${history.name} version history`}>
      <div className="flex justify-between gap-3"><h3 className="font-semibold">{history.name} · version history</h3>
        <button type="button" onClick={() => setHistory(null)}>Close history</button></div>
      {history.rows.map(row => <div key={row.id} className="border-t mt-3 pt-3 text-sm">
        <p>Version {row.doc_version} · {row.is_current ? "Current" : "Previous"} · {row.verification_status}</p>
        <p className="break-words">{row.file_name} · {formatISTDateTime(row.created_at)}</p>
        {row.rejection_reason && <p className="text-danger">Reason: {row.rejection_reason}</p>}
        {row.download_url && <a className="text-primary" href={row.download_url} target="_blank" rel="noreferrer">Preview this version</a>}
      </div>)}
    </section>}
  </div>;
}
