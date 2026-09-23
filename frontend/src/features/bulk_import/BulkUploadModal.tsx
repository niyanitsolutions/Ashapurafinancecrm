import { useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { apiRequest } from "@/shared/api/client";
import { getCurrentCoordinates } from "@/shared/geolocation";

export interface ImportRow {
  number: number;
  values: Record<string, string>;
  status: string;
  error: string;
}
export interface ImportPreview {
  batch_id: string;
  state: "preview" | "processing" | "completed";
  total: number;
  valid: number;
  invalid: number;
  duplicate: number;
  imported: number;
  failed: number;
  processing: number;
  rows: ImportRow[];
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function BulkUploadModal({ kind, onClose, onImported }: {
  kind: "leads" | "insurance";
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState("");
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const base = `/bulk-import/${kind}`;
  const run = async (label: string, operation: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(label);
    setError("");
    try { await operation(); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to process the file. Please check the file format and try again."); }
    finally { busyRef.current = false; setBusy(""); }
  };
  const validate = () => run("Validating file...", async () => {
    if (!file || !/\.(csv|xlsx)$/i.test(file.name)) throw new Error("Choose a CSV or XLSX file.");
    if (!file.size || file.size > 5 * 1024 * 1024) throw new Error("Choose a non-empty file no larger than 5 MB.");
    const body = new FormData();
    body.append("file", file);
    setPreview(await apiRequest<ImportPreview>(`${base}/preview`, { method: "POST", body }));
  });
  const confirm = () => run("Importing records...", async () => {
    if (!preview || preview.state !== "preview") return;
    const coords = kind === "leads" ? await getCurrentCoordinates() : {};
    let result: ImportPreview;
    do {
      result = await apiRequest<ImportPreview>(`${base}/confirm`, { method: "POST", body: JSON.stringify({ batch_id: preview.batch_id, ...coords }) });
      setPreview(result);
      onImported();
    } while (result.state === "preview" && result.valid > 0);
  });
  const sample = () => run("Preparing sample...", async () => {
    const result = await apiRequest<{ filename: string; content: string }>(`${base}/sample`);
    const bytes = Uint8Array.from(atob(result.content), (char) => char.charCodeAt(0));
    download(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), result.filename);
  });
  const errors = () => {
    if (!preview) return;
    // Quoting alone does not prevent spreadsheet formula injection in downloaded CSV.
    const escape = (value: string) => `"${(/^[\s]*[=+\-@]/.test(value) ? `'${value}` : value).replaceAll('"', '""')}"`;
    const lines = [["Row", "Status", "Error"], ...preview.rows.filter((row) => row.error || row.status === "processing").map((row) => [String(row.number), row.status, row.error || "Processing or interrupted. Check existing records before retrying."])];
    download(new Blob(["\uFEFF" + lines.map((row) => row.map(escape).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }), `${kind}-import-errors.csv`);
  };
  return <Modal open title={`Bulk Upload ${kind === "insurance" ? "Insurance Leads" : "Leads"}`} size="lg" onClose={() => { if (!busyRef.current) onClose(); }} footer={<>
    <Button variant="secondary" disabled={!!busy} onClick={onClose}>{preview?.state === "completed" ? "Close" : "Cancel"}</Button>
    {!preview && <Button disabled={!!busy || !file} onClick={() => void validate()}>Continue</Button>}
    {preview?.state === "preview" && <Button disabled={!!busy || !preview.valid} onClick={() => void confirm()}>Import {preview.valid} Records</Button>}
  </>}>
    <div className="space-y-4">
      <ErrorBanner message={error} />
      {busy && <p role="status" className="text-sm text-text/70">{busy}</p>}
      {!preview ? <>
        <p className="text-sm text-text/70">Upload CSV or Excel (.xlsx). Maximum 5 MB and 500 records. Download the sample for supported columns and available products.</p>
        <label className="block text-sm font-medium">Choose CSV / Excel File
          <input className="mt-2 block w-full rounded border border-border p-2" type="file" accept=".csv,.xlsx" disabled={!!busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(""); }} />
        </label>
        <Button variant="secondary" disabled={!!busy} onClick={() => void sample()}>Download Sample Excel</Button>
      </> : <>
        <h3 className="font-semibold">{preview.state === "completed" ? "Import Result" : "Bulk Upload Preview"}</h3>
        <p role="status" className="text-sm">Total: {preview.total} · Valid: {preview.valid} · Imported: {preview.imported} · Duplicates: {preview.duplicate} · Invalid: {preview.invalid} · Failed: {preview.failed}</p>
        {preview.state === "completed" && <p className="text-sm">{preview.imported} leads imported successfully. {preview.duplicate} duplicates, {preview.invalid} invalid, {preview.failed} failed.</p>}
        {preview.state === "preview" && !preview.valid && <p>No valid records found.</p>}
        {preview.state === "processing" && <p role="alert">This batch is processing or was interrupted. Check existing records before retrying. Reopen the same file to refresh its progress.</p>}
        <p className="text-sm text-text/70">{kind === "insurance" ? "Insurance allows additional applications for existing customers, just like manual creation." : "Active duplicate mobiles are excluded. Rows with Assign To will use the normal assignment workflow."} The same file cannot be imported again for 24 hours.</p>
        <Button variant="secondary" disabled={!!busy} onClick={errors}>Download Error Report</Button>
        <div className="max-h-80 overflow-auto rounded border border-border">
          <table className="w-full text-left text-sm"><thead><tr><th className="p-2">Row</th><th className="p-2">Record</th><th className="p-2">Status / Errors</th></tr></thead>
            <tbody>{preview.rows.map((row) => <tr key={row.number} className="border-t border-border"><td className="p-2">{row.number}</td><td className="p-2"><details><summary>{row.values.full_name || "Unnamed record"} {row.values.mobile}</summary>{Object.entries(row.values).map(([key, value]) => <div key={key}>{key.replaceAll("_", " ")}: {value}</div>)}</details></td><td className="p-2">{row.status}{row.error && `: ${row.error}`}</td></tr>)}</tbody>
          </table>
        </div>
      </>}
    </div>
  </Modal>;
}
