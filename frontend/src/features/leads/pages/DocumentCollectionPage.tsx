import { UpdateStageModal } from "@/features/leads/components/UpdateStageModal";
import { getLead, type LeadListItem } from "@/features/leads/api";
import { BulkUploadModal } from "@/features/bulk_import/BulkUploadModal";
import { GenerateLinkModal } from "@/features/leads/components/GenerateLinkModal";
import { MoveApplicationToLoanManagementModal } from "@/features/leads/components/MoveApplicationToLoanManagementModal";
import { DateInput } from "@/components/forms/DateInput";
import { Fragment, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { usePermissions } from "@/features/access_control/usePermissions";
import { deleteRecord } from "@/features/bin/api";
import { BulkAssignmentModal, type AssignmentResult } from "@/features/leads/components/BulkAssignmentModal";
import { apiRequest } from "@/shared/api/client";
import { formatISTDate } from "@/shared/dateFormat";

type Filters = Record<string, string>;
interface Group { id: string; name: string; customer_code?: string; mobile?: string; application_count: number; latest_submission?: string; primary?: Application }
interface Application { id: string; record_kind?: string; lead_id?: string; lead_code?: string; application_code: string; customer_code?: string; product_name: string; product_category?: string; status: string; assigned_to_name?: string; submitted_at?: string; created_at?: string; source_name?: string; submission_source?: string; customer_status?: string; customer_name?: string; mobile?: string }
interface Page<T> { items: T[]; total: number; page: number; page_size: number }
const base = "/leads/document-collection";
const dimensionLabels: Record<string, string> = { assigned_to: "Assigned To", assigned_by: "Assigned By", product_id: "Product", source_id: "Source", branch_id: "Branch", follow_up_status: "Follow-up status", bank_id: "Bank / NBFC" };
const dateLabels: Record<string, string> = { created_from: "Created from", follow_up_from: "Next follow-up from", follow_up_until: "Next follow-up until" };
const filterKeys = new Set(["search", ...Object.keys(dimensionLabels), ...Object.keys(dateLabels), "follow_up_employee", "application_status", "document_status", "customer_status", "product_category", "overdue", "customer_id"]);
const columns = ["", "Application / Lead Code", "Customer Name", "Mobile", "Source", "Product", "Assigned To", "Application Status", "Customer Account Status", "Created On", "Actions"];
function Status({ value }: { value?: string }) { return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${value === "submitted" ? "bg-blue-50 text-blue-700" : value === "active" ? "bg-green-50 text-green-700" : "bg-orange-50 text-orange-800"}`}>{value === "draft" ? "Pending" : value ? value.charAt(0).toUpperCase()+value.slice(1) : "Not recorded"}</span>; }
function sourceName(app?: Application) { return app?.source_name || (app?.submission_source && app.submission_source !== "unknown" ? app.submission_source.replaceAll("_", " ") : "Not recorded"); }
const cell = "px-4 py-4 text-sm align-middle";
function RecordCells({ app, group }: { app?: Application; group: Group }) { return <>
  <td className={`${cell} whitespace-nowrap`}>{app?.id ? <Link className="font-medium text-primary hover:underline" to={app.record_kind === "lead" ? `/leads/${app.id}` : `/applications/${app.id}?from=document-collection${group.customer_code ? `&customer_id=${encodeURIComponent(group.id)}` : ""}`}>{app.application_code}</Link> : group.customer_code || "Not recorded"}{group.customer_code && <Link className="mt-1 block text-xs text-textSecondary hover:underline" to={`/leads/document-collection?customer_id=${encodeURIComponent(group.id)}&expand=${encodeURIComponent(group.id)}`}>{group.customer_code}</Link>}</td>
  <td className={`${cell} font-medium`}>{app?.customer_name || group.name}</td><td className={`${cell} whitespace-nowrap`}>{app?.mobile || group.mobile || "Not recorded"}</td>
  <td className={cell}><span className="inline-flex whitespace-nowrap rounded-full bg-blue-50 px-2.5 py-1 text-xs capitalize text-blue-700">{sourceName(app)}</span></td>
  <td className={`${cell} whitespace-nowrap`}>{app?.product_name || "Not recorded"}</td><td className={cell}>{app?.assigned_to_name || "Unassigned"}</td><td className={cell}><Status value={app?.status} /></td><td className={cell}><Status value={app?.customer_status} /></td>
  <td className={`${cell} whitespace-nowrap`}>{app?.created_at ? formatISTDate(app.created_at) : "Not recorded"}</td>
</>; }

const control = "w-full rounded-lg border border-border bg-card px-3 py-2 text-sm";

function Applications({ group, query, selected, toggle, onDelete, owner, onChanged }: { group: Group; query: string; selected: Set<string>; toggle: (id: string) => void; onDelete: (id: string) => void; owner: boolean; onChanged: () => void }) {
  const { can } = usePermissions();
  const [link,setLink] = useState<Application | null>(null);
  const [move,setMove] = useState<Application | null>(null);
  const [updating,setUpdating] = useState<LeadListItem | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Application> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setData(null); setError(null);
    apiRequest<Page<Application>>(`${base}/grouped?${query}&group_key=${encodeURIComponent(group.id)}&page=${page}&page_size=25`)
      .then(result => { if (active) setData(result); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [group.id, page, query]);
  return <div role="region" aria-label={`Applications for ${group.name}`} className="space-y-3 border-t border-border bg-background p-4">
    <ErrorBanner message={error} />
    {!data && !error && <p role="status">Loading applications...</p>}
    <div className="overflow-x-auto"><table className="w-full min-w-[1100px] text-left font-sans"><thead className="bg-background text-xs uppercase text-textSecondary"><tr>{columns.map((name,i) => <th key={i} scope="col" className="px-4 py-3">{name || "Select"}</th>)}</tr></thead><tbody>
    {data?.items.map((app, i) => <tr key={app.id} className={`border-t border-border ${page === 1 && i === 0 ? "bg-primary/5" : "bg-card"}`}>
      <td className={cell}>{owner && app.record_kind !== "lead" && <input aria-label={`Select ${app.application_code}`} type="checkbox" checked={selected.has(app.id)} onChange={() => toggle(app.id)} />}</td>
      <RecordCells app={app} group={group} />
      <td className={`${cell} min-w-[240px]`}><div className="flex flex-wrap gap-2"><Link className="rounded-full border border-border px-3 py-1.5 text-xs text-primary" to={app.record_kind === "lead" ? `/leads/${app.id}` : `/applications/${app.id}?from=document-collection${group.customer_code ? `&customer_id=${encodeURIComponent(group.id)}` : ""}`}>View</Link>
      {app.lead_id && can("leads:leads", "edit") && <><Link className="text-primary underline" to={`/leads/${app.lead_id}/edit`}>Edit Lead</Link><Button size="sm" variant="secondary" onClick={() => setLink(app)}>Generate Link</Button><Button size="sm" variant="secondary" onClick={async () => { try { setUpdating(await getLead(app.lead_id!)); } catch(err) { setError(err instanceof Error ? err.message : "Unable to load Lead update."); } }}>Update</Button></>}
      {!app.lead_id && app.product_category === "loan" && can("leads:leads", "edit") && <Button size="sm" variant="secondary" onClick={() => setMove(app)}>Update</Button>}
      {owner && app.record_kind !== "lead" && <Button size="sm" variant="danger" onClick={() => onDelete(app.id)}>Delete application</Button>}
      </div></td>
    </tr>)}
    </tbody></table></div>
    {link?.lead_id && <GenerateLinkModal leadId={link.lead_id} leadCode={link.lead_code || link.application_code} onClose={() => setLink(null)} />}
    {updating && <UpdateStageModal lead={updating} onClose={() => setUpdating(null)} onChanged={() => { setUpdating(null); onChanged(); }} />}
    {move && <MoveApplicationToLoanManagementModal lead={{ application_id: move.id, lead_code: move.application_code }} onClose={() => setMove(null)} onChanged={() => { setMove(null); onChanged(); }} />}
    {data && <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / 25))} totalItems={data.total} pageSize={25} onPageChange={setPage} itemLabel="applications" />}
  </div>;
}

export function DocumentCollectionPage() {
  const { isOwner, can } = usePermissions();
  const [bulk,setBulk] = useState(false);
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [10,25,50,100,200].includes(Number(params.get("page_size"))) ? Number(params.get("page_size")) : 200;
  const applied = Object.fromEntries([...params].filter(([key]) => filterKeys.has(key)));
  const [draft, setDraft] = useState<Filters>(applied);
  const [options, setOptions] = useState<Record<string, { value: string; label: string }[]>>({});
  const [optionsLoading,setOptionsLoading] = useState(true);
  const [optionsError,setOptionsError] = useState<string | null>(null);
  const [data, setData] = useState<Page<Group> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assign, setAssign] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<AssignmentResult | null>(null);
  const query = new URLSearchParams(applied).toString();
  const focusedGroup = params.get("expand");
  useEffect(() => {
    const text = draft.search || "";
    const timer = setTimeout(() => {
      const current = Object.fromEntries(new URLSearchParams(query));
      if (text !== (current.search || "")) {
        if (text) current.search = text; else delete current.search;
        setParams({ ...current, page: "1", page_size: String(pageSize) });
      }
    },350);
    return () => clearTimeout(timer);
  },[draft.search,query,pageSize,setParams]);
  useEffect(() => { setDraft(Object.fromEntries(new URLSearchParams(query))); },[query]);
  useEffect(() => {
    let active = true;
    apiRequest<typeof options>(`${base}/filter-options`).then(value => { if(active) setOptions(value); })
      .catch(err => { if(active) setOptionsError(err instanceof Error ? err.message : "Unable to load filter choices."); })
      .finally(() => { if(active) setOptionsLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setData(null); setError(null); setOpen(new Set(focusedGroup ? [focusedGroup] : []));
    apiRequest<Page<Group>>(`${base}/grouped?${query}&page=${page}&page_size=${pageSize}`)
      .then(rows => { if (active) setData(rows); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [query, page, pageSize, revision, focusedGroup]);
  useEffect(() => { setSelected(new Set()); },[query,page,pageSize]);
  function navigate(changes: Filters) { setParams({ ...applied, page: String(page), page_size: String(pageSize), ...changes }); }
  const update = (key: string, value: string) => setDraft(old => ({ ...old, [key]: value }));
  const toggle = (id: string) => setSelected(old => { const next = new Set(old); if (next.has(id)) next.delete(id); else if (next.size < 100) next.add(id); return next; });
  return <section className="space-y-4 p-4 sm:p-6 lg:p-8">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Document Collection</h2>{can("leads:leads","create") && <div className="flex gap-3"><Button variant="secondary" onClick={() => setBulk(true)}>Bulk Upload</Button><Link className="rounded-lg bg-primary px-4 py-2 text-sm text-white" to="/leads/create">Create Lead</Link></div>}</div>
    {bulk && <BulkUploadModal kind="leads" onClose={() => setBulk(false)} onImported={() => { setBulk(false); setRevision(v => v+1); }} />}
    <ErrorBanner message={error || optionsError} />
    <form className="space-y-4 rounded-card border border-border bg-card p-4" onSubmit={e => { e.preventDefault(); setParams({ ...Object.fromEntries(Object.entries(draft).filter(([,v]) => v)), page: "1", page_size: String(pageSize) }); }}>
      <label className="block text-sm">Search customers and applications<input className={`${control} mt-1`} type="search" placeholder="Name, mobile, email, Customer ID, Application ID or Lead code" value={draft.search || ""} onChange={e => update("search", e.target.value)} /></label>
      <details><summary className="cursor-pointer font-medium">Advanced filters</summary>{optionsLoading && <p role="status" className="mt-2 text-sm text-textSecondary">Loading filter choices...</p>}<div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(dimensionLabels).map(([key,label]) => <label key={key} className="text-sm">{label}<select aria-label={label} disabled={optionsLoading} className={control} value={draft[key] || ""} onChange={e => update(key,e.target.value)}><option value="">All</option>{key === "assigned_to" && <option value="__unassigned__">Unassigned</option>}{(options[key] || []).map(option => <option key={String(option.value)} value={String(option.value)}>{String(option.label)}</option>)}</select></label>)}
        <label className="text-sm">Follow-up employee<select aria-label="Follow-up employee" disabled={optionsLoading} className={control} value={draft.follow_up_employee || ""} onChange={e => update("follow_up_employee",e.target.value)}><option value="">All</option>{(options.follow_up_employee || options.assigned_to || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
        {Object.entries(dateLabels).map(([key,label]) => <label key={key} className="text-sm">{label}<DateInput className={control} value={draft[key] || ""} onChange={e => update(key,e.target.value)} /></label>)}
        <label className="text-sm">Application status<select aria-label="Application status" className={control} value={draft.application_status || ""} onChange={e => update("application_status",e.target.value)}><option value="">All</option><option value="draft">Pending</option><option value="submitted">Submitted</option></select></label>
        <label className="text-sm">Documents<select aria-label="Documents" className={control} value={draft.document_status || ""} onChange={e => update("document_status",e.target.value)}>{["", "pending", "submitted", "verified", "rejected", "missing"].map(value => <option key={value} value={value}>{value || "All documents"}</option>)}</select></label>
        <label className="text-sm">Customer account status<select aria-label="Customer account status" className={control} value={draft.customer_status || ""} onChange={e => update("customer_status",e.target.value)}><option value="">All</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label>
        <label className="text-sm">Product category<select aria-label="Product category" className={control} value={draft.product_category || ""} onChange={e => update("product_category",e.target.value)}><option value="">All</option><option value="loan">Loan</option><option value="insurance">Insurance</option></select></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.overdue === "true"} onChange={e => update("overdue", e.target.checked ? "true" : "")} />Overdue follow-ups</label>
      </div></details>
      <div className="flex flex-wrap gap-3"><Button type="submit">Apply Filters</Button><Button variant="secondary" onClick={() => { setDraft({}); setParams({ page: "1", page_size: String(pageSize) }); }}>Clear Filters</Button></div>
      {Object.values(applied).filter(Boolean).length > 0 && <p className="text-sm text-textSecondary">{Object.values(applied).filter(Boolean).length} active filters</p>}
    </form>
    {isOwner && selected.size > 0 && <div className="flex flex-wrap items-center gap-3"><span>{selected.size} Applications selected (maximum 100)</span><Button onClick={() => setAssign(true)}>Assign Selected</Button><Button variant="secondary" onClick={() => setSelected(new Set())}>Clear Selection</Button></div>}
    {result && <div role="status"><p>Assigned: {result.assigned} | Skipped: {result.skipped} | Failed: {result.failed}</p><ul className="text-sm">{result.results.filter(row => row.status !== "assigned").map(row => <li key={row.id} className="break-all">{row.id}: {row.reason}</li>)}</ul></div>}
    {!data && !error && <p role="status">Loading customers...</p>}
    <div className="overflow-hidden rounded-card border border-border bg-card"><div className="overflow-x-auto"><table aria-label="Document Collection customers" className="w-full min-w-[1200px] text-left font-sans">
      <thead className="bg-background text-xs uppercase text-textSecondary"><tr>{columns.map((name,i) => <th key={i} scope="col" className="px-4 py-3">{name || "Select"}</th>)}</tr></thead><tbody>
      {data?.items.map(group => <Fragment key={group.id}>
        <tr data-customer-group={group.id} className="border-t border-border hover:bg-background/50">
          <td className={cell}>{isOwner && <input aria-label={`Select ${group.name}`} type="checkbox" disabled={group.application_count !== 1 || !group.primary?.id || group.primary.record_kind === "lead"} title={group.application_count !== 1 ? "Expand to select individual applications" : undefined} checked={Boolean(group.primary?.id && selected.has(group.primary.id))} onChange={() => { if(group.primary?.id) toggle(group.primary.id); }} />}</td>
          <RecordCells app={group.primary} group={group} />
          <td className={cell}><Button variant="secondary" size="sm" aria-expanded={open.has(group.id)} aria-controls={`applications-${group.id}`} onClick={() => setOpen(old => { const next = new Set(old); if(next.has(group.id)) next.delete(group.id); else next.add(group.id); return next; })}>{open.has(group.id) ? "Collapse" : "Expand"}</Button><span className="mt-1 block text-xs text-textSecondary">{group.application_count} applications</span>{group.latest_submission && <small className="mt-1 block text-textSecondary">Latest submitted {formatISTDate(group.latest_submission)}</small>}</td>
        </tr>
        {open.has(group.id) && <tr id={`applications-${group.id}`}><td colSpan={11} className="p-0"><Applications group={group} query={query} selected={selected} toggle={toggle} owner={isOwner} onDelete={setDeleting} onChanged={() => setRevision(v => v+1)} /></td></tr>}
      </Fragment>)}
      </tbody></table></div></div>
    {data && data.total === 0 && <p>No matching customers or applications.</p>}
    {data && <Pagination page={page} totalPages={Math.max(1,Math.ceil(data.total / pageSize))} totalItems={data.total} pageSize={pageSize} onPageChange={p => navigate({ page: String(p) })} onPageSizeChange={size => navigate({ page: "1", page_size: String(size) })} pageSizeOptions={[10,25,50,100,200]} itemLabel="customers" />}
    {assign && <BulkAssignmentModal collection="applications" ids={[...selected]} onClose={() => setAssign(false)} onDone={r => { setResult(r); setAssign(false); setSelected(new Set(r.results.filter(row => row.status !== "assigned").map(row => row.id))); setRevision(v => v + 1); }} />}
    {deleting && <Modal open title="Delete application?" onClose={() => { if (!busy) setDeleting(null); }}><p className="mb-4 text-sm">Move this application to Bin. Its Customer and other applications remain intact. Recovery follows the existing retention policy.</p><div className="flex gap-3"><Button variant="danger" loading={busy} onClick={async () => { setBusy(true); try { await deleteRecord("applications",deleting); setDeleting(null); setRevision(v => v+1); } catch(err) { setError(err instanceof Error ? err.message : "Deletion failed."); } finally { setBusy(false); } }}>Confirm Delete</Button><Button variant="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel</Button></div></Modal>}
  </section>;
}
