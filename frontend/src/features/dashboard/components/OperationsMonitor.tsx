import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { useDashboardFilters } from "@/features/dashboard/DashboardFiltersContext";
import { apiRequest } from "@/shared/api/client";
import { formatISTDateTime } from "@/shared/dateFormat";

interface Summary {
  tabs: Record<string, number>; cohort_leads: number; definition: string;
  followups: { overdue: number; today: number; upcoming: number };
  priorities: { id: string; name: string; reference: string; due_at: string; route: string }[];
  workload: { employee_id: string | null; employee: string; leads: number; stages: Record<string, number> }[];
  workload_total: number;
  applications?: { submitted: number; draft: number };
  daily_followups?: { total: number; overdue: number; priorities: { id: string; name: string; due_date: string; route: string }[] };
  recent_submissions?: { id: string; name: string; reference: string; submitted_at: string; route: string }[];
  assignment?: { enabled: boolean; pending: number; failures: number; total_assigned: number };
}
const tabPaths: Record<string, string> = { fresh: "/leads", my_leads: "/leads/my", document_collection: "/leads/document-collection", rejected: "/leads/rejected", assigned: "/leads/assigned" };

export function OperationsMonitor() {
  const { isOwner, can } = usePermissions();
  const { userId } = useAuth();
  const { filters } = useDashboardFilters();
  const [employee, setEmployee] = useState("");
  const [stage, setStage] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ range: filters.range, page: String(page) });
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.productCategory) params.set("product_category", filters.productCategory);
  if (filters.sourceId) params.set("source_id", filters.sourceId);
  if (isOwner && employee) params.set("employee", employee);
  if (stage) params.set("stage", stage);
  const query = useQuery({ queryKey: ["operations-monitor", userId, params.toString()], queryFn: () => apiRequest<Summary>(`/dashboard/operations?${params}`), enabled: can("leads:leads", "view"), refetchInterval: 30000 });
  const employees = useQuery({ queryKey: ["monitor-employees", userId], queryFn: () => apiRequest<{ employees: { id: string; name: string }[] }>("/leads/auto-assignment"), enabled: isOwner });
  if (!can("leads:leads", "view")) return null;
  const data = query.data;
  return <section className="space-y-4 rounded-card border border-border bg-card p-4 sm:p-6" aria-label="CRM operations">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">{isOwner ? "Team operations" : "My work and priorities"}</h3>{isOwner && <Link className="text-sm text-primary underline" to="/settings/auto-assignment">Auto Assignment Settings</Link>}</div>
    <div className="flex flex-wrap gap-3">
      {isOwner && <label className="grid gap-1 text-sm">Employee<select className="rounded-lg border border-border bg-card p-2" value={employee} onChange={event => { setEmployee(event.target.value); setPage(1); }}><option value="">All employees</option>{employees.data?.employees.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
      <label className="grid gap-1 text-sm">Lead stage<select className="rounded-lg border border-border bg-card p-2" value={stage} onChange={event => { setStage(event.target.value); setPage(1); }}><option value="">All stages</option>{["fresh", "assigned", "document_collection", "loan_management", "rejected"].map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
    </div>
    <ErrorBanner message={query.error?.message ?? employees.error?.message ?? null} />
    {query.isLoading && <p role="status">Loading operational monitoring…</p>}
    {data && <>
      <p className="text-xs text-textSecondary">{data.definition} Application counts use creation date and product; lead-source and stage filters apply to leads only.</p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">{Object.entries(data.tabs).filter(([key]) => tabPaths[key]).map(([key, value]) => <Link key={key} to={tabPaths[key]} className="rounded-lg border border-border p-3 text-sm"><span className="capitalize">{key.replaceAll("_", " ")}</span><strong className="block text-xl">{value}</strong></Link>)}</div>
      {data.assignment && <p className="text-sm">Rotation {data.assignment.enabled ? "enabled" : "paused"} · {data.assignment.total_assigned} automatic assignments recorded · <Link className="text-primary underline" to="/settings/auto-assignment">{data.assignment.pending} waiting / {data.assignment.failures} needing attention</Link></p>}
      <div className="grid gap-6 lg:grid-cols-2"><div><h4 className="mb-2 font-medium">Scheduled lead follow-ups</h4><p className="mb-3 text-sm">{data.followups.overdue} overdue · {data.followups.today} today · {data.followups.upcoming} upcoming</p>
        <ul className="space-y-2 text-sm">{data.priorities.map(row => <li key={row.id}><Link className="text-primary underline" to={row.route}>{row.name} · {row.reference}</Link><span className="block text-xs text-textSecondary">{formatISTDateTime(row.due_at)}</span></li>)}</ul>{!data.priorities.length && <p className="text-sm text-textSecondary">No overdue or today's scheduled lead follow-ups.</p>}
      </div><div><h4 className="mb-2 font-medium">Recent submitted applications</h4>{data.applications ? <p className="mb-3 text-sm">{data.applications.submitted} submitted · {data.applications.draft} drafts in selected creation period</p> : <p className="text-sm text-textSecondary">Customer viewing permission is required.</p>}
        <ul className="space-y-2 text-sm">{data.recent_submissions?.map(row => <li key={row.id}><Link className="text-primary underline" to={row.route}>{row.name} ? {row.reference}</Link><span className="block text-xs text-textSecondary">{formatISTDateTime(row.submitted_at)}</span></li>)}</ul>{data.applications && !data.recent_submissions?.length && <p className="text-sm text-textSecondary">No submitted applications in this period.</p>}
      </div></div>
      {data.daily_followups && <div><h4 className="mb-2 font-medium">Daily Follow-up workspace</h4>
        <p className="mb-2 text-sm">{data.daily_followups.total} current records &middot; <Link className="text-primary underline" to="/daily-operations/follow-ups?overdue=true">{data.daily_followups.overdue} overdue</Link></p>
        <p className="mb-2 text-xs text-textSecondary">Uses current Daily Follow-up rules and employee scope across all dates and products. Open Daily Update for its full filters.</p>
        <ul className="space-y-2 text-sm">{data.daily_followups.priorities.map(row => <li key={row.id}><Link className="text-primary underline" to={row.route}>{row.name} &middot; Open daily follow-up</Link></li>)}</ul>
      </div>}
      <h4 className="font-medium">Lead workload in selected period ({data.cohort_leads})</h4>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Employee", "Leads", "Fresh", "Assigned stage", "Document Collection", "Rejected"].map(label => <th key={label} className="whitespace-nowrap border-b border-border p-2">{label}</th>)}</tr></thead><tbody>{data.workload.map(row => <tr key={row.employee_id ?? "unassigned"}><td className="p-2">{row.employee}</td><td className="p-2">{row.leads}</td>{["fresh", "assigned", "document_collection", "rejected"].map(key => <td key={key} className="p-2">{row.stages[key] ?? 0}</td>)}</tr>)}</tbody></table></div>
      {!data.workload.length && <p className="text-sm text-textSecondary">No leads match these filters.</p>}
      <div className="flex items-center gap-3"><Button variant="secondary" size="sm" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous workload</Button><span className="text-sm">Page {page}</span><Button variant="secondary" size="sm" disabled={page * 20 >= data.workload_total} onClick={() => setPage(page + 1)}>Next workload</Button></div>
    </>}
  </section>;
}
