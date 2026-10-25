import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Table, TableBody, TableContainer, TableHead, TableHeadRow, TableRow, Th, Td } from "@/components/tables/DataTable";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";
import { areas, base, download, downloadBlob, type Area, type ImportResult, type Preview } from "./api";

export function TransferCentre() {
  const { can } = usePermissions();
  const availableAreas = Object.entries(areas).filter(([key]) => can(`daily_operations:${key}`, "view") && (can(`daily_operations:${key}`, "import") || can(`daily_operations:${key}`, "export")));
  const [selectedArea, setArea] = useState<Area>("follow-ups");
  const area = (availableAreas.some(([key]) => key === selectedArea) ? selectedArea : availableAreas[0]?.[0] ?? selectedArea) as Area;
  const [file, setFile] = useState<File | null>(null);
  const [allowUpdates, setAllowUpdates] = useState(false);
  const [mapping, setMapping] = useState("{}"); const [preview, setPreview] = useState<Preview | null>(null); const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [confirmed, setConfirmed] = useState(false);
  const reset = () => { setPreview(null); setResult(null); setConfirmed(false); };
  async function run(action: () => Promise<void>) { setBusy(true); setError(null); try { await action(); } catch (err) { setError(err instanceof Error ? err.message : "Transfer failed."); } finally { setBusy(false); } }
  async function upload() {
    if (!file) { setError("Choose a CSV or XLSX file."); return; }
    reset();
    await run(async () => { const body = new FormData(); body.append("file", file); body.append("mapping", mapping); body.append("allow_updates", String(allowUpdates)); setPreview(await apiRequest<Preview>(`${base}/transfers/${area}/preview`, { method: "POST", body })); });
  }
  const reportErrors = result?.errors ?? preview?.rows.filter(row => row.errors.length).map(row => ({ row: row.row, errors: row.errors })) ?? [];
  function errorReport() {
    const safe = (value: string) => '"' + value.replace(/"/g, '""').replace(/^[=+@-]/, "'$&") + '"';
    const rows = ["Row,Column,Error", ...reportErrors.flatMap(row => row.errors.map(err => [String(row.row), safe(err.column), safe(err.message)].join(",")))];
    downloadBlob(new Blob([rows.join("\r\n")], { type: "text/csv" }), "import-errors.csv");
  }
  return <SimplePageLayout title="Import & Export Centre" subtitle="Choose a work area, upload your sheet, and check the rows before saving.">
    <ErrorBanner message={error} />
    <div className="max-w-3xl space-y-4">
      <SelectField label="Destination work area" value={area} options={availableAreas.map(([value, label]) => ({ value, label }))} onChange={e => { setArea(e.target.value as Area); setFile(null); reset(); }} />
      {can(`daily_operations:${area}`, "export") && <Link className="text-primary underline" to={`/daily-operations/${area}`}>Open {areas[area]} to filter and export records</Link>}
      <p className="text-sm text-textSecondary">Use the template to get started. Excel and CSV files up to 5 MB / 500 rows are supported. Existing records are kept unless you choose to update them.</p>
      {can(`daily_operations:${area}`, "import") ? <>
        <div className="flex gap-2">{(["csv", "xlsx"] as const).map(format => <Button key={format} variant="secondary" disabled={busy} onClick={() => void run(async () => { await download(`${base}/transfers/${area}/template?format=${format}`, `${area}-template.${format}`); })}>Template {format.toUpperCase()}</Button>)}</div>
        <FormField key={area} label="Upload CSV or XLSX" type="file" accept=".csv,.xlsx" onChange={e => { setFile(e.target.files?.[0] ?? null); reset(); }} />
        <details className="rounded-lg border border-border p-3"><summary className="cursor-pointer text-sm">Advanced import options</summary><div className="mt-3 space-y-3">
          <FormField label="Column mapping (JSON: uploaded heading to destination field)" value={mapping} onChange={e => { setMapping(e.target.value); reset(); }} />
          <p className="text-sm">Template columns are recognized automatically. If your headings differ, map them here, for example {JSON.stringify({ "My date heading": "date" })}.</p>
          {["follow-ups", "progress", "issues"].includes(area) && <label className="flex gap-2"><input type="checkbox" checked={allowUpdates} onChange={e => { setAllowUpdates(e.target.checked); reset(); }} />Update existing rows using the RECORD ID and VERSION from an export.</label>}
          <p className="text-xs text-textSecondary">Valid rows are saved individually. Retries skip saved rows. Session files are Owner-only corrections, not new sign-ins. Official loan amounts remain in Loan Management.</p>
        </div></details>
        <Button disabled={!file || busy} onClick={() => void upload()}>Validate & preview</Button>
      </> : <p role="status">You can export this work area. Ask the Owner to make corrections.</p>}
    </div>
    {busy && <p role="status" className="my-4">Processing…</p>}
    {preview && <section className="mt-6" aria-label="Import preview">
      <h2 className="text-lg font-semibold">Preview</h2><p className="my-3">{preview.rows.filter(row => !row.errors.length).length} ready; {preview.rows.filter(row => row.errors.length).length} need attention. Only valid rows will be saved.</p>
      <TableContainer><Table><TableHead><TableHeadRow><Th>Row</Th><Th>Mapped values</Th><Th>Validation</Th></TableHeadRow></TableHead><TableBody>{preview.rows.map(row => <TableRow key={row.row}><Td>{row.row}</Td><Td><dl>{Object.entries(row.values).filter(([key, value]) => value && !["lead_id", "case_id", "record_id", "version", "assigned_to"].includes(key)).map(([key, value]) => <div key={key}><dt className="inline font-medium">{key.replaceAll("_", " ")}: </dt><dd className="inline break-all">{value} </dd></div>)}</dl></Td><Td>{row.errors.length ? row.errors.map((err, index) => <p key={index}>{err.column}: {err.message}</p>) : row.duplicate ? "Exact duplicate: will skip" : "Valid"}</Td></TableRow>)}</TableBody></Table></TableContainer>
      {!result && <div className="my-4 space-y-3"><label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I reviewed these rows and want to save them.</label><Button disabled={!confirmed || busy || !preview.rows.some(row => !row.errors.length)} onClick={() => void run(async () => { setResult(await apiRequest<ImportResult>(`${base}/transfers/${preview.id}/confirm`, { method: "POST", body: JSON.stringify({ confirmed: true }) })); })}>Confirm import</Button></div>}
    </section>}
    {result && <p role="status" className="my-4">Inserted: {result.inserted}. Updated: {result.updated}. Skipped: {result.skipped}. Rejected: {result.rejected}.</p>}
    {!!reportErrors.length && <Button variant="secondary" onClick={errorReport}>Download error report</Button>}
  </SimplePageLayout>;
}
