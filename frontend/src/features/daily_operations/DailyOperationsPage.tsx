import { TransferScope, TransferCheck, TransferTag } from "@/features/daily_operations/HandoverTools";
import { FollowUpIdentitySearch } from "./FollowUpIdentitySearch";
import { IdentityReview } from "./IdentityReview";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableContainer, TableHead, TableHeadRow, TableRow, Th, Td } from "@/components/tables/DataTable";
import { useAuth } from "@/features/auth/useAuth";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";
import { formatISTDate, todayISTDateString } from "@/shared/dateFormat";
import { areas, base, businessTime, deleteRecord, download, getLookups, getRecord, issueStatuses, listRecords, text, type Area, type Row } from "./api";
import { useStatusOptions, statusRowStyle } from "./statusOptions";
import { RecordForm } from "./RecordForm";
import { EmployeeNameField } from "./EmployeeNameField";

const FILTER_KEYS = ["outcome", "month", "sort", "search", "status", "date_from", "date_to", "employee_name", "bank", "loan_type", "overdue", "old_days"];
const columns: Record<Area, [string, string][]> = {
  "follow-ups": [["date", "DATE"], ["loan_type", "LOAN TYPE"], ["bank", "BANK / NBFCs"], ["customer_name", "CX NAME"], ["customer_number", "CX NUMBER"], ["remarks", "TODAY CASE STATUS"], ["remarks_date", "REMARKS DATE"], ["status", "FOLLOW PENDING"], ["due_date", "NEXT FOLLOW-UP"], ["reeligible_date", "RE-ELIGIBLE DATE"], ["employee_name", "EMPLOYEE NAME"]],
  progress: [["date", "DATE"], ["customer_name", "CX NAME"], ["customer_number", "CX NUMBER"], ["bank", "BANK / NBFC"], ["status", "TODAY CASE STAGE"], ["next_action", "WHAT'S NEXT?"], ["due_date", "NEXT FOLLOW-UP"], ["approved_amount", "APPROVED AMOUNT"], ["employee_name", "EMPLOYEE NAME"]],
  sessions: [["date", "DATE"], ["employee_name", "EMPLOYEE NAME"], ["login_at", "LOGIN TIME"], ["logout_at", "LOGOUT TIME"], ["recorded_seconds", "DURATION"], ["status", "STATUS"]],
  issues: [["date", "DATE"], ["employee_name", "EMPLOYEE NAME"], ["inquiry", "INQUIRY OR ISSUE"], ["assigned_to_name", "ASSIGNED TO"], ["priority", "PRIORITY"], ["status", "STATUS"], ["resolution_notes", "RESOLUTION NOTES"]],
};
const pretty = (value: unknown) => text(value).replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const money = (value: unknown) => value == null ? "—" : Number(value).toLocaleString("en-IN", { style: "currency", currency: "INR" });

export function DailyOperationsPage({ area }: { area: Area }) {
  const { userId } = useAuth();
  const { can, isOwner, loading } = usePermissions();
  const statuses = useStatusOptions(area === "follow-ups" && can("daily_operations:follow-ups", "view"), true);
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  // Keep consecutive filter interactions together while router transitions commit.
  const pendingParams = useRef(searchParams);
  const exportMenu = useRef<HTMLDetailsElement>(null);
  useEffect(() => { pendingParams.current = searchParams; }, [searchParams]);
  const filters: Record<string, string> = { sort: "-date", ...Object.fromEntries(FILTER_KEYS.filter(key => area === "sessions" || key !== "month").filter(key => searchParams.has(key)).map(key => [key, searchParams.get(key)!])) };
  const reeligibleView = area === "follow-ups" && searchParams.get("workflow") === "reeligible";
  if (area === "follow-ups") filters.workflow = reeligibleView ? "reeligible" : "normal";
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 && requestedPage <= 100000 ? requestedPage : 1;
  const requestedSize = Number(searchParams.get("page_size") ?? (area === "follow-ups" ? "200" : "20"));
  const pageSize = [20, 50, 100, 150, 200].includes(requestedSize) ? requestedSize : (area === "follow-ups" ? 200 : 20);
  const allowed = can(`daily_operations:${area}`, "view");
  const params = new URLSearchParams({ ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)), page: String(page), page_size: String(pageSize) });
  const query = useQuery({ queryKey: ["daily-operations", userId, area, params.toString()], queryFn: () => listRecords(area, params.toString()), enabled: !loading && allowed, refetchInterval: area === "sessions" || area === "follow-ups" ? 30000 : false });
  const lookup = useQuery({ queryKey: ["daily-lookups", userId, area, ""], queryFn: () => getLookups("", area === "progress"), enabled: !loading && allowed });
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [history, setHistory] = useState<Row | null>(null);
  const [removing, setRemoving] = useState<Row | null>(null);
  const [requesting, setRequesting] = useState<Row | null>(null);
  const [requestReason, setRequestReason] = useState("");
  const [standaloneIdentity,setStandaloneIdentity]=useState<Record<string,string>|undefined>();
  const [identitySearch,setIdentitySearch]=useState(false);
  const [identityReview,setIdentityReview] = useState(false);
  const [extraColumns, setExtraColumns] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const linkedRecordId = searchParams.get("record");
  useEffect(() => {
    if (area !== "follow-ups" || !allowed || !linkedRecordId) return;
    let active = true;
    void getRecord(area, linkedRecordId).then(row => { if (active) setEditing(row); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to open linked record."); });
    return () => { active = false; };
  }, [area, allowed, linkedRecordId]);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(pendingParams.current);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("page"); pendingParams.current = next; setSearchParams(next, { replace: true });
  }
  const filterField = (key: string, label: string, type = "text") => <FormField label={label} type={type} value={filters[key] ?? ""} onChange={event => filter(key, event.target.value)} />;
  const refresh = () => { void client.invalidateQueries({ queryKey: ["daily-operations"] }); };
  async function inspect(row: Row, edit: boolean) {
    setError(null);
    try {
      const full = area === "sessions" ? row : await getRecord(area, row.id);
      if (edit) setEditing(full); else setHistory(full);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to open this row."); }
  }
  async function exportFile(format: "csv" | "xlsx") {
    if (exportMenu.current) exportMenu.current.open = false;
    try { await download(`${base}/${area}/export?${params}&format=${format}`, `${area}.${format}`); }
    catch (err) { setError(err instanceof Error ? err.message : "Export failed."); }
  }
  const visibleColumns = [...(reeligibleView ? columns["follow-ups"].filter(([key]) => !["remarks_date", "status", "due_date", "reeligible_date", "employee_name"].includes(key)).concat([["reeligible_date", "RE-ELIGIBLE DATE"], ["employee_name", "EMPLOYEE NAME"]]) : columns[area]), ...(area === "progress" && extraColumns ? [["login_date", "DATE OF LOGIN"], ["age_days", "AGE (DAYS)"], ["disbursed_at", "DATE OF DISBURSE"], ["disbursed_amount", "DISBURSED AMOUNT"], ["updated_at", "UPDATE DATE"]] : [])];
  function cell(key: string, value: unknown) {
    if (key === "banks") return Array.isArray(value)?value.map(bank=>String((bank as {name:string}).name)).join(", "):text(value);
    if (key === "bank" && Array.isArray(value)) return value.map(bank=>String((bank as {name:string}).name)).join(", ");
    if (key === "approved_amount" || key === "disbursed_amount") return money(value);
    if (key === "recorded_seconds") return value == null ? "Open session" : `${Math.floor(Number(value) / 3600)}h ${Math.floor(Number(value) % 3600 / 60)}m`;
    if (["login_at", "logout_at", "updated_at"].includes(key)) return businessTime(value);
    if (["date", "remarks_date", "due_date", "reeligible_date", "login_date", "disbursed_at"].includes(key)) return value ? formatISTDate(String(value)) : "—";
    if (key === "status" && area === "follow-ups") return text(value);
    if (key === "status" || key === "priority") return pretty(value);
    return text(value);
  }
  return <TransferScope collection={area === "follow-ups" ? "daily_follow_ups" : area === "issues" ? "operational_issues" : undefined} ids={(query.data?.items||[]).map(r=>r.id)} allowed={can(`daily_operations:${area}`,"assign")} onTransferred={refresh}><SimplePageLayout title={reeligibleView ? "Re-Eligible" : areas[area]} subtitle={area === "sessions" ? "Login and logout are recorded automatically. Request a correction if something is missing." : "Add a row, update it as work progresses, and keep your daily notes together."} actions={<>
    {can(`daily_operations:${area}`, "export") && <details ref={exportMenu} className="relative"><summary className="cursor-pointer rounded-lg border border-border bg-card px-4 py-2.5 text-sm">Export</summary><div className="absolute right-0 z-10 mt-1 grid rounded-lg border border-border bg-card shadow-card p-1"><Button variant="ghost" onClick={() => void exportFile("xlsx")}>Excel</Button><Button variant="ghost" onClick={() => void exportFile("csv")}>CSV</Button></div></details>}
    {area === "follow-ups" && allowed && <Button variant={reeligibleView ? "primary" : "secondary"} aria-pressed={reeligibleView} onClick={() => filter("workflow", "reeligible")}>Re-Eligible</Button>}
    {reeligibleView && <Button variant="secondary" onClick={() => filter("workflow", "")}>Daily Follow-up Data</Button>}
    {area !== "sessions" && can(`daily_operations:${area}`, "create") && <Button onClick={() => { setNotice(""); setStandaloneIdentity(undefined); if(area === "follow-ups")setIdentitySearch(true);else setEditing(null); }}>+ Add record</Button>}
  </>}>
    {!loading && !allowed ? <p role="alert">You do not have permission to view this work area.</p> : <>
      {isOwner && area === "follow-ups" && <Button variant="secondary" onClick={()=>setIdentityReview(true)}>Preview identity review</Button>}
      {identityReview && <IdentityReview onClose={()=>setIdentityReview(false)} onChanged={refresh} />}
      <ErrorBanner message={error ?? (query.error instanceof Error ? query.error.message : null)} />
      {notice && <p role="status" className="mb-3 rounded-lg bg-primary/5 p-3 text-sm">{notice}</p>}
      <div className="flex flex-wrap items-start gap-x-4 mb-2">
        {area === "sessions" && <div className="min-w-48 flex-1"><FormField label="Month" type="month" required value={filters.month ?? query.data?.month ?? ""} onChange={event => filter("month", event.target.value)} /></div>}
        {area !== "sessions" && <div className="min-w-52 flex-1">{filterField("search", "Search")}</div>}
        <div className="min-w-48 flex-1"><EmployeeNameField label="Employee name" value={filters.employee_name ?? ""} options={lookup.data?.employees ?? []} onChange={name => filter("employee_name", name)} /></div>
        <details className="min-w-48 self-start mt-7"><summary className="cursor-pointer rounded-lg border border-border bg-card px-4 py-2.5 text-sm">More filters</summary><div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-4 rounded-lg border border-border bg-card p-4">
          {filterField("date_from", "From date", "date")}{filterField("date_to", "To date", "date")}
          {area === "progress" ? filterField("status", "Case stage") : area !== "sessions" && <SelectField label="Status" placeholder="All statuses" value={filters.status ?? ""} options={area === "issues" ? issueStatuses.map(value=>({value,label:pretty(value)})) : (statuses.data??[]).map(row=>({value:row.value,label:row.name+(row.is_active?"":" (archived)")}))} onChange={event => filter("status", event.target.value)} />}
          {["follow-ups", "progress"].includes(area) && <>{filterField("bank", "Bank / NBFC")}{filterField("loan_type", "Loan type")}</>}
          {area === "follow-ups" && <SelectField label="Due" value={filters.overdue ?? ""} options={[{ value: "", label: "All follow-ups" }, { value: "true", label: "Overdue only" }]} onChange={event => filter("overdue", event.target.value)} />}
          {area !== "sessions" && <SelectField label="Sort" value={filters.sort} options={(area === "progress" ? [["-date", "Latest update"], ["created_at", "Oldest first"]] : [["-date", "Newest date"], ["date", "Oldest date"], ["status", "Status"]]).map(([value, label]) => ({ value, label }))} onChange={event => filter("sort", event.target.value)} />}
          <Button variant="ghost" onClick={() => { pendingParams.current = new URLSearchParams(); setSearchParams({}); }}>Clear filters</Button>
        </div></details>
      </div>
      {area === "progress" && <label className="mb-3 flex gap-2 text-sm text-textSecondary"><input type="checkbox" checked={extraColumns} onChange={event => setExtraColumns(event.target.checked)} />Show login and disbursement details</label>}
      {query.isLoading || loading ? <p role="status">Loading records…</p> : query.isError ? <Button variant="secondary" onClick={() => void query.refetch()}>Retry</Button> : <>
        <TableContainer><Table aria-label={`${areas[area]} records`}><TableHead><TableHeadRow>{visibleColumns.map(([key, label]) => <Th key={key}>{label}</Th>)}<Th className="sticky right-0 bg-card">Actions</Th></TableHeadRow></TableHead><TableBody>
          {!query.data?.items.length ? <TableRow><Td colSpan={visibleColumns.length + 1}><div className="py-8 text-center text-textSecondary">No records match these filters.{area !== "sessions" && " Use Add record to enter your first row."}</div></Td></TableRow> : query.data.items.map(row => <TableRow key={row.id} style={area === "follow-ups" ? statusRowStyle(text(row.status),statuses.data??[]) : undefined} className={area === "follow-ups" ? "[&>td]:!bg-inherit hover:brightness-95 focus-within:outline focus-within:outline-2 focus-within:outline-current" : ""}>
            {visibleColumns.map(([key]) => <Td key={key} className="py-2.5 max-w-xs"><span title={key==="bank"&&area==="follow-ups"?cell("banks",row.banks):undefined} className={key === "status" ? "inline-block rounded-md bg-primary/5 px-2 py-1 text-xs font-medium" : key==="bank"?"line-clamp-2":""}>{cell(key, area==="follow-ups"&&key==="status"?(row.status_display||row.status):area==="follow-ups"&&key==="bank"?(row.banks||row.bank):row[key])}</span>{key === "customer_name" && area === "follow-ups" && <><TransferTag id={row.id}/>{Boolean(row.application_code)&&<dl className="mt-1 text-xs font-normal"><dt>Application / Customer</dt><dd>{String(row.application_code)} / {String(row.customer_code||"Not recorded")}</dd><dt>Email</dt><dd>{String(row.email||"Not recorded")}</dd><dt>Application / Account status</dt><dd>{String(row.application_status||"")} / {String(row.account_status||"")}</dd><dt>Movement / Created</dt><dd>{String(row.movement_status||"")} / {businessTime(row.application_created_at)}</dd>{Boolean(row.disbursed_at)&&<><dt>Disbursement</dt><dd>{money(row.approved_amount)} approved; {money(row.disbursed_amount)} disbursed {businessTime(row.disbursed_at)}</dd><dt>Top-up</dt><dd>{String(row.top_up_period||"Not scheduled")}</dd></>}</dl>}</>}{key === "customer_name" && area === "follow-ups" && <span className="mt-1 block text-xs font-medium">{text(row.relationship_label) || (row.application_id ? "Linked - Application" : row.customer_id ? "Linked - Customer" : row.lead_id ? "Linked - Lead" : "Standalone - Unlinked")}</span>}{key === "customer_name" && Boolean(row.identity_warning) && <span role="status" className="block text-xs text-orange-700">{String(row.identity_warning)}</span>}{area === "progress" && key === "customer_name" && row.source === "manual" && <span className="block text-xs text-textSecondary">Daily entry</span>}</Td>)}
            <Td className={`sticky right-0 py-2 ${area === "follow-ups" ? "bg-inherit" : "bg-card"}`}><div className="flex items-center gap-1"><TransferCheck id={row.id}/>{area === "follow-ups" && Boolean(row.application_id) && <Link className="text-primary text-xs underline" to={`/applications/${row.application_id}`}>View Application</Link>}
              {(area !== "sessions" && can(`daily_operations:${area}`, "edit")) && <Button variant="ghost" size="sm" className={area === "follow-ups" ? "!text-inherit focus-visible:!outline-current" : ""} onClick={() => void inspect(row, true)}>Edit</Button>}
              <Button variant="ghost" size="sm" className={area === "follow-ups" ? "!text-inherit focus-visible:!outline-current" : ""} onClick={() => void inspect(row, false)}>{area === "sessions" ? "Session history" : "History"}</Button>
              {area === "sessions" && !isOwner && <Button variant="ghost" size="sm" onClick={() => { setRequesting(row); setRequestReason(""); }}>Request correction</Button>}
              {isOwner && area !== "sessions" && <Button variant="danger" size="sm" className={area === "follow-ups" ? "!text-inherit hover:brightness-95 focus-visible:!outline-current" : ""} onClick={() => setRemoving(row)}>Delete</Button>}
            </div></Td>
          </TableRow>)}
        </TableBody></Table></TableContainer>
        {!!query.data?.items.length && <Pagination pageSizeOptions={[20, 50, 100, 150, 200]} onPageSizeChange={value => { const next = new URLSearchParams(pendingParams.current); next.set("page_size", String(value)); next.delete("page"); pendingParams.current = next; setSearchParams(next); }} page={page} pageSize={pageSize} totalItems={query.data.total} totalPages={Math.ceil(query.data.total / pageSize)} onPageChange={value => { const next = new URLSearchParams(pendingParams.current); next.set("page", String(value)); pendingParams.current = next; setSearchParams(next); }} />}
      </>}
      {area === "sessions" && <p className="mt-3 text-xs text-textSecondary">Eligible session time includes the existing inactivity allowance and is not verified productive work. Times use {query.data?.business_timezone ?? "the business timezone"}.</p>}
      {query.data?.metrics && <details className="mt-4 text-sm"><summary className="cursor-pointer text-textSecondary">Official loan totals</summary><p className="mt-2">Approved offers: {money(query.data.metrics.approved_amount)} · Verified disbursed: {money(query.data.metrics.disbursed_amount)}. Manual daily entries do not change these totals.</p></details>}
    </>}
    {identitySearch && <FollowUpIdentitySearch onClose={()=>setIdentitySearch(false)} onSelected={row=>{setIdentitySearch(false);setEditing(row);}} onStandalone={identity=>{setIdentitySearch(false);setStandaloneIdentity(identity);setEditing(null);}}/>}
    <Modal open={editing !== undefined} title={editing ? "Edit record" : "Add record"} onClose={() => setEditing(undefined)} size="lg">
      {editing && Boolean(editing.working_key) && <p className="mb-4 flex flex-wrap gap-3 text-sm">
        {editing.lead_id ? <Link className="text-primary underline" to={`/leads/${String(editing.lead_id)}`}>Original lead</Link> : null}
        {editing.application_id ? <Link className="text-primary underline" to={`/applications/${String(editing.application_id)}`}>Original application</Link> : null}
        <span>Linked workspace · business status changes remain in the original record.</span>
      </p>}
      {editing !== undefined && <RecordForm initialIdentity={editing ? undefined : standaloneIdentity} key={editing?.id ?? "new"} area={area} record={editing ?? undefined} onCancel={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); setNotice("Record saved."); refresh(); }} />}
    </Modal>
    <Modal open={!!history} title="Record history" onClose={() => setHistory(null)} size="lg">
      {area === "sessions" && <div className="space-y-3">{((history?.sessions ?? []) as Row[]).map(session => <div key={session.id} className="rounded-lg border border-border p-3 text-sm">
        <p>Daily segment: {businessTime(session.segment_start_at ?? session.login_at)} &rarr; {businessTime(session.segment_end_at ?? session.logout_at)}{session.segment_status === "day_boundary" && " (day boundary)"}</p>
        <p>Actual login: {businessTime(session.login_at)} ? Actual logout: {businessTime(session.logout_at)}</p>
        <p>{cell("recorded_seconds", session.recorded_seconds)} ? {pretty(session.status)} ? {pretty(session.end_reason)}</p>
        {isOwner && can("daily_operations:sessions", "edit") && <Button variant="ghost" size="sm" onClick={() => { setEditing(session); setHistory(null); }}>Correct session</Button>}
      </div>)}</div>}
      <ol className="space-y-4">{(history?.history as { at: string; source?: string; actor_id?:string; actor_name?:string; before?: Record<string, unknown>; after?: Record<string, unknown> }[] ?? []).map((event, index) => <li key={index} className="border-b border-border pb-3"><p className="text-sm font-medium">{businessTime(event.at)} | {event.actor_name||event.actor_id||"System"}{event.source === "automatic" && " - Automatic transition"}</p><dl className="mt-2 text-sm">{Object.entries(event.after ?? {}).filter(([key, value]) => !["lead_id", "case_id", "assigned_to", "source", "status_label", "customer_interest_option_id", "customer_interest_status_snapshot"].includes(key) && value !== event.before?.[key]).map(([key, value]) => <div key={key} className="grid grid-cols-2 gap-3"><dt className="text-textSecondary">{pretty(key)}</dt><dd className="break-words">{event.before ? `${text(key==="status"?(event.before.status_label||event.before[key]):event.before[key])} → ` : ""}{cell(key, key==="status"?(event.after?.status_label||value):value)}</dd></div>)}</dl></li>)}</ol>
    </Modal>
    <ConfirmDialog open={!!removing} title="Delete this daily record?" message="This removes the row from Daily Update and keeps its history. Linked loans and original sign-in records are retained." confirmLabel="Delete record" confirmVariant="danger" onClose={() => setRemoving(null)} onConfirm={async () => {
      if (!removing) return;
      try { await deleteRecord(area, removing); setRemoving(null); setNotice("Record deleted from Daily Update."); refresh(); }
      catch (err) { setRemoving(null); setError(err instanceof Error ? err.message : "Unable to delete this record."); }
    }} />
    <Modal open={!!requesting} title="Request a login/logout correction" onClose={() => setRequesting(null)}>
      <form onSubmit={async event => { event.preventDefault(); try { await apiRequest(`${base}/issues`, { method: "POST", body: JSON.stringify({ date: todayISTDateString(), inquiry: `Login/logout correction for ${businessTime(requesting?.login_at)}: ${requestReason}` }) }); setRequesting(null); setNotice("Correction request saved. The Owner can review it in Inquiry or Issue."); } catch (err) { setError(err instanceof Error ? err.message : "Unable to save the request."); } }}>
        <TextareaField label="What needs correcting?" rows={3} required minLength={5} value={requestReason} onChange={event => setRequestReason(event.target.value)} />
        <Button type="submit">Send request</Button>
      </form>
    </Modal>
  </SimplePageLayout></TransferScope>;
}
