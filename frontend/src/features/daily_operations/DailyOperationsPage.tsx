import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableContainer, TableHead, TableHeadRow, TableRow, Th, Td } from "@/components/tables/DataTable";
import { useAuth } from "@/features/auth/useAuth";
import { usePermissions } from "@/features/access_control/usePermissions";
import { areas, base, businessTime, download, followStatuses, getRecord, issueStatuses, listRecords, text, type Area, type Row } from "./api";
import { RecordForm } from "./RecordForm";

const columns: Record<Area, [string, string][]> = {
  "follow-ups": [["date", "DATE"], ["loan_type", "LOAN TYPE"], ["bank", "BANK / NBFCs"], ["customer_name", "CX NAME"], ["customer_number", "CX NUMBER"], ["status", "TODAY CASE STATUS"], ["remarks_date", "REMARKS DATE"], ["due_date", "FOLLOW PENDING"], ["next_action", "NEXT ACTION"], ["employee_name", "EMPLOYEE NAME"]],
  progress: [["date", "DATE"], ["bank", "APPLIED BANK OR NBFC"], ["lead_id", "LEAD ID"], ["customer_name", "CX NAME"], ["customer_number", "CX NUMBER"], ["status", "TODAY CASE STAGE"], ["next_action", "WHAT'S NEXT FOLLOW-UP TMROW"], ["due_date", "FOLLOW PENDING"], ["age_days", "OLD CASES UNDER PROGRESS (days)"], ["login_date", "DATE OF LOGIN"], ["approved_amount", "APPROVED LOAN AMT"], ["updated_at", "UPDATE DATE"], ["disbursed_at", "DATE OF DISBURSE"], ["disbursed_amount", "LOAN AMOUNT"]],
  sessions: [["date", "DATE"], ["employee_name", "EMPLOYEE NAME"], ["login_at", "LOGIN TIME"], ["logout_at", "LOGOUT TIME"], ["recorded_seconds", "RECORDED SECONDS"], ["status", "SESSION STATUS"], ["corrected", "CORRECTED"]],
  issues: [["date", "DATE"], ["employee_name", "EMPLOYEE NAME"], ["inquiry", "INQUIRY OR ISSUE"], ["id", "Issue ID"], ["assigned_to", "Assigned To"], ["priority", "Priority"], ["status", "Status"], ["resolution_notes", "Resolution Notes"], ["resolved_at", "Resolved Date"]],
};

export function DailyOperationsPage({ area }: { area: Area }) {
  const { userId } = useAuth(); const { can, isOwner, loading } = usePermissions(); const client = useQueryClient();
  const [filters, setFilters] = useState<Record<string, string>>({ sort: "-date" }); const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [history, setHistory] = useState<Row | null>(null); const [error, setError] = useState<string | null>(null); const [success, setSuccess] = useState(false);
  const allowed = can(`daily_operations:${area}`, "view");
  const params = new URLSearchParams({ ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)), page: String(page), page_size: "20" });
  const query = useQuery({ queryKey: ["daily-operations", userId, area, params.toString()], queryFn: () => listRecords(area, params.toString()), enabled: !loading && allowed });
  const filter = (key: string, value: string) => { setFilters(old => ({ ...old, [key]: value })); setPage(1); };
  const filterField = (key: string, label: string, type = "text") => <FormField label={label} type={type} value={filters[key] ?? ""} onChange={e => filter(key, e.target.value)} />;
  async function inspect(row: Row, edit: boolean) {
    try { const full = area === "sessions" ? row : await getRecord(area, row.id); if (edit) setEditing(full); else setHistory(full); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to open record."); }
  }
  async function exportFile(format: "csv" | "xlsx") { try { await download(`${base}/${area}/export?${params}&format=${format}`, `${area}.${format}`); } catch (err) { setError(err instanceof Error ? err.message : "Export failed."); } }
  return <SimplePageLayout title={areas[area]} subtitle={area === "sessions" ? "Authentication session families, displayed in Asia/Kolkata. Missing logout remains unknown. These are not payroll hours. Date filters use the original login date." : "Persisted CRM operations. Dates use Asia/Kolkata. Loan stages and financial amounts are managed in Loan Management."} actions={<>
    <Link className="text-primary underline" to="/daily-operations/transfers">Import & Export Centre</Link>
    {can(`daily_operations:${area}`, "export") && <><Button variant="secondary" onClick={() => void exportFile("csv")}>Export CSV</Button><Button variant="secondary" onClick={() => void exportFile("xlsx")}>Export XLSX</Button></>}
    {["follow-ups", "issues"].includes(area) && can(`daily_operations:${area}`, "create") && <Button onClick={() => setEditing(null)}>Create record</Button>}
  </>}>
    {!loading && !allowed ? <p role="alert">You do not have permission to view this work area.</p> : <>
      <ErrorBanner message={error ?? (query.error instanceof Error ? query.error.message : null)} />
      {success && <p role="status" className="mb-4">Record saved.</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-4">
        {area !== "sessions" && filterField("search", area === "progress" ? "Search case code" : "Search")}
        {filterField("date_from", "From date", "date")}{filterField("date_to", "To date", "date")}{filterField("employee", "Employee CRM ID")}
        {["follow-ups", "progress"].includes(area) && <>{filterField("bank", "Bank / NBFC")}{filterField("loan_type", "Loan type")}</>}
        {["follow-ups", "issues"].includes(area) && <SelectField label="Status" placeholder="All statuses" value={filters.status ?? ""} options={(area === "issues" ? issueStatuses : followStatuses).map(value => ({ value, label: value }))} onChange={e => filter("status", e.target.value)} />}
        {area === "progress" && <>{filterField("status", "Canonical case stage")}{filterField("old_days", "Old cases: minimum age (days)", "number")}</>}
        {area === "follow-ups" && <SelectField label="Overdue" value={filters.overdue ?? ""} options={[{ value: "", label: "All follow-ups" }, { value: "true", label: "Overdue only" }]} onChange={e => filter("overdue", e.target.value)} />}
        {area !== "sessions" && <SelectField label="Sort" value={filters.sort} options={(area === "progress" ? [["-updated_at", "Latest update"], ["created_at", "Oldest login"], ["current_status", "Stage"]] : [["-date", "Newest date"], ["date", "Oldest date"], ["status", "Status"]]).map(([value, label]) => ({ value, label }))} onChange={e => filter("sort", e.target.value)} />}
      </div>
      {query.data?.statuses && <p className="mb-4 text-sm" role="status">{Object.entries(query.data.statuses).map(([status, count]) => `${status}: ${count}`).join(" · ")}</p>}
      {query.data?.metrics && <p className="mb-4 text-sm">Approved offer amounts: {query.data.metrics.approved_amount.toLocaleString("en-IN", { style: "currency", currency: "INR" })} · Verified disbursed amounts: {query.data.metrics.disbursed_amount.toLocaleString("en-IN", { style: "currency", currency: "INR" })}. Totals cover the filtered cases, across all pages.</p>}
      {area === "follow-ups" && query.data?.breakdowns && <details className="mb-4"><summary className="cursor-pointer text-sm">Operational breakdowns (top 100 groups)</summary><p className="text-sm my-2">Counts represent follow-up records. Multiple attempts for one lead count separately.</p><div className="grid sm:grid-cols-3 gap-4">{Object.entries(query.data.breakdowns).map(([key, entries]) => <div key={key}><h2 className="font-medium">{({ by_employee: "By employee ID", by_bank: "By bank / NBFC", by_loan_type: "By loan type" })[key]}</h2><ul>{entries.map(entry => <li key={entry.label}>{entry.label}: {entry.count}</li>)}</ul></div>)}</div></details>}
      {query.isLoading ? <p role="status">Loading records…</p> : query.isError ? <Button variant="secondary" onClick={() => void query.refetch()}>Retry</Button> : !query.data?.items.length ? <p>No records match these filters.</p> : <>
        <TableContainer><Table><TableHead><TableHeadRow>{columns[area].map(([key, label]) => <Th key={key}>{label}</Th>)}<Th>Actions</Th></TableHeadRow></TableHead><TableBody>{query.data.items.map(row => <TableRow key={row.id}>
          {columns[area].map(([key]) => <Td key={key}>{["login_at", "logout_at", "updated_at", "resolved_at", "disbursed_at", "login_date"].includes(key) ? businessTime(row[key]) : text(row[key])}</Td>)}
          <Td><div className="flex gap-2">
            {area === "progress" ? <Link className="text-primary underline" to={`/loan-management/cases/${row.id}`}>Open loan & history</Link> : <>
              {area !== "sessions" && <Button variant="ghost" size="sm" onClick={() => void inspect(row, false)}>History</Button>}
              {can(`daily_operations:${area}`, "edit") && (area !== "sessions" || isOwner) && <Button variant="secondary" size="sm" onClick={() => void inspect(row, true)}>{area === "sessions" ? "Correct" : "Edit"}</Button>}
            </>}
          </div></Td>
        </TableRow>)}</TableBody></Table></TableContainer>
        <Pagination page={page} pageSize={20} totalItems={query.data.total} totalPages={Math.ceil(query.data.total / 20)} onPageChange={setPage} />
      </>}
    </>}
    <Modal open={editing !== undefined} title={editing ? "Edit record" : "Create record"} onClose={() => setEditing(undefined)} size="lg">
      {editing !== undefined && <RecordForm key={editing?.id ?? "new"} area={area} record={editing ?? undefined} onCancel={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); setSuccess(true); void client.invalidateQueries({ queryKey: ["daily-operations"] }); }} />}
    </Modal>
    <Modal open={!!history} title="Activity history" onClose={() => setHistory(null)} size="lg">
      {history && <><p className="mb-3">Lead: {text(history.lead_code ?? history.lead_id)} · Owner: {text(history.assigned_to)}</p><ol className="space-y-4">{(history.history as { at: string; actor_id: string; before: unknown; after: unknown }[] ?? []).map((event, index) => <li key={index} className="border-b border-border pb-3"><p>{businessTime(event.at)} · Actor {event.actor_id}</p><pre className="whitespace-pre-wrap break-words text-xs mt-2">{JSON.stringify({ before: event.before, after: event.after }, null, 2)}</pre></li>)}</ol></>}
    </Modal>
  </SimplePageLayout>;
}
