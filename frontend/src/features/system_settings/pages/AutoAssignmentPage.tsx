import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Modal } from "@/components/overlays/Modal";
import type { AssignmentResult } from "@/features/leads/components/BulkAssignmentModal";

interface Settings { enabled: boolean; employee_ids: string[]; version: number; sequence: number; employees: { id: string; name: string; active: boolean; assigned_leads?: number }[] }
interface Pending { items: { id: string; collection: string; error: string | null; route: string }[]; total: number }
interface History { items: { id: string; event_type: string; created_at: string; actor_name?: string; employee_name?: string; metadata?: { collection?: string; employee_id?: string; record_id?: string; lead_id?: string; application_id?: string; sequence?: number } }[]; total: number }
const base = "/leads/auto-assignment";

export function AutoAssignmentPage() {
  const { isOwner } = usePermissions();
  const client = useQueryClient();
  const [draft, setDraft] = useState<{ enabled: boolean; employee_ids: string[]; version: number } | null>(null);
  const [page, setPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [retryPreview, setRetryPreview] = useState<AssignmentResult | null>(null);
  const [retryRecords, setRetryRecords] = useState<{ id: string; collection: string }[]>([]);
  const [retryResult, setRetryResult] = useState<AssignmentResult | null>(null);
  const settings = useQuery({ queryKey: ["auto-assignment"], queryFn: () => apiRequest<Settings>(base), enabled: isOwner });
  const pending = useQuery({ queryKey: ["auto-assignment", "pending", page], queryFn: () => apiRequest<Pending>(`${base}/pending?page=${page}`), enabled: isOwner });
  const history = useQuery({ queryKey: ["auto-assignment", "history", historyPage], queryFn: () => apiRequest<History>(`${base}/history?page=${historyPage}`), enabled: isOwner });
  const value = draft ?? settings.data;
  const update = (changes: Partial<NonNullable<typeof draft>>) => { if (value) setDraft({ enabled: value.enabled, employee_ids: value.employee_ids, version: value.version, ...changes }); };
  async function action(work: () => Promise<unknown>, message: string) {
    setBusy(true); setError(null); setNotice("");
    try { await work(); setNotice(message); await client.invalidateQueries({ queryKey: ["auto-assignment"] }); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to update assignment."); }
    finally { setBusy(false); }
  }
  if (!isOwner) return <SimplePageLayout title="Auto Assignment Settings"><p>Only an Owner can manage automatic assignment.</p></SimplePageLayout>;
  return <SimplePageLayout title="Auto Assignment Settings" subtitle="Distribute new intake in selection order. Existing assignments remain in place.">
    <ErrorBanner message={error ?? (settings.error ?? pending.error ?? history.error)?.message ?? null} />
    {notice && <p role="status" className="mb-4 text-sm text-success">{notice}</p>}
    {settings.isLoading && <p role="status">Loading assignment settings…</p>}
    {value && <form className="space-y-4 rounded-card border border-border bg-card p-5" onSubmit={event => {
      event.preventDefault(); void action(async () => { await apiRequest(base, { method: "PUT", body: JSON.stringify({ enabled: value.enabled, employee_ids: value.employee_ids, version: value.version }) }); setDraft(null); }, "Assignment settings saved.");
    }}>
      <label className="flex items-center gap-2"><input type="checkbox" checked={value.enabled} onChange={event => update({ enabled: event.target.checked })} /> Enable automatic assignment</label>
      <p className="text-sm text-textSecondary">Uncheck to pause. Inactive accounts and employees without access to the incoming product module are skipped. Select employees in the desired rotation order.</p>
      <fieldset className="grid gap-3 sm:grid-cols-2"><legend className="mb-2 font-medium">Assignment pool</legend>{settings.data?.employees.map(employee => <label key={employee.id} className="flex items-center gap-2 rounded-lg border border-border p-3">
        <input type="checkbox" checked={value.employee_ids.includes(employee.id)} disabled={!employee.active && !value.employee_ids.includes(employee.id)} onChange={event => update({ employee_ids: event.target.checked ? [...value.employee_ids, employee.id] : value.employee_ids.filter(id => id !== employee.id) })} />
        {employee.name}{!employee.active && " (inactive)"}{employee.assigned_leads != null && <span aria-hidden="true" className="text-xs text-textSecondary">{employee.assigned_leads} leads</span>}{value.employee_ids.includes(employee.id) && <span className="ml-auto text-sm text-textSecondary">#{value.employee_ids.indexOf(employee.id) + 1}</span>}
      </label>)}</fieldset>
      {!settings.data?.employees.length && <p>No employee accounts are available.</p>}
      <Button type="submit" disabled={busy}>Save settings</Button>
    </form>}
    <section className="mt-6 space-y-3 rounded-card border border-border bg-card p-5"><h3 className="font-semibold">Unassigned intake for review ({pending.data?.total ?? 0})</h3>
      <p className="text-sm text-textSecondary">This includes historical unassigned intake. Review a preview before retrying this page; existing assignments are preserved.</p>
      <Button disabled={busy || !value?.enabled || !pending.data?.items.length} onClick={() => void action(async () => {
        const records = pending.data!.items.map(({ id, collection }) => ({ id, collection }));
        const result = await apiRequest<AssignmentResult>(`${base}/bulk-retry`, { method: "POST", body: JSON.stringify({ records }) });
        setRetryRecords(records); setRetryPreview(result);
      }, "Retry preview ready. No assignment has been changed.")}>Preview retry for this page</Button>
      {retryResult && <div role="status" className="text-sm"><p>Successfully assigned: {retryResult.assigned} · Skipped: {retryResult.skipped} · Failed: {retryResult.failed}</p><ul>{retryResult.results.filter(row => row.status !== "assigned").map(row => <li key={`${row.collection}:${row.id}`} className="break-all">{row.id}: {row.reason}</li>)}</ul></div>}
      <p className="text-sm text-textSecondary">Retry uses the original record. A paused rotation must be enabled first. A request still processing may take two minutes to become retryable.</p>
      {pending.data?.items.map(row => <div key={`${row.collection}:${row.id}`} className="flex flex-wrap items-center gap-3 border-t border-border pt-3 text-sm">
        <Link className="text-primary underline break-all" to={row.route}>Open {row.collection === "leads" ? "lead" : "application"} {row.id}</Link><span>{row.error ? "No eligible assignee or assignment service unavailable" : "Awaiting assignment"}</span>
        <Button size="sm" disabled={busy || !value?.enabled} onClick={() => void action(async () => {
          const records = [{ id: row.id, collection: row.collection }];
          const result = await apiRequest<AssignmentResult>(`${base}/bulk-retry`, { method: "POST", body: JSON.stringify({ records }) });
          setRetryRecords(records); setRetryPreview(result);
        }, "Retry preview ready. No assignment has been changed.")}>Preview retry</Button>
      </div>)}
      <div className="flex items-center gap-3"><Button variant="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page}</span><Button variant="secondary" disabled={page * 20 >= (pending.data?.total ?? 0)} onClick={() => setPage(page + 1)}>Next</Button></div>
    </section>
    {retryPreview && <Modal open title="Confirm unassigned intake retry" onClose={() => { if (!busy) setRetryPreview(null); }}><div className="space-y-4 text-sm">
      <p>{retryPreview.eligible} eligible · {retryPreview.skipped} skipped · {retryPreview.failed} failed. Confirm assigning these original records using the current configured rotation, including any historical rows on this page.</p>
      <ul>{retryPreview.results.map(row => <li key={`${row.collection}:${row.id}`} className="break-all">{row.id}: {row.reason}</li>)}</ul>
      <div className="flex flex-wrap gap-2"><Button disabled={busy || !retryPreview.eligible} onClick={() => void action(async () => {
        const result = await apiRequest<AssignmentResult>(`${base}/bulk-retry`, { method: "POST", body: JSON.stringify({ records: retryRecords, preview_id: retryPreview.preview_id }) });
        setRetryResult(result); setRetryPreview(null);
      }, "Retry finished. Review the individual results.")}>Confirm retry</Button><Button variant="secondary" disabled={busy} onClick={() => setRetryPreview(null)}>Cancel</Button></div>
    </div></Modal>}
    <section className="mt-6 space-y-3 rounded-card border border-border bg-card p-5"><h3 className="font-semibold">Assignment history</h3>
      {history.data?.items.map(row => {
        const recordId = row.metadata?.record_id ?? row.metadata?.lead_id ?? row.metadata?.application_id;
        const application = row.metadata?.collection === "applications" || Boolean(row.metadata?.application_id);
        const labels: Record<string, string> = { crm_auto_assigned: "Automatically assigned", lead_assigned: "Lead assigned", lead_unassigned: "Lead unassigned", application_assigned: "Application assigned" };
        return <p key={row.id} className="break-words text-sm">{formatISTDateTime(row.created_at)} &middot; {labels[row.event_type] ?? "Assignment changed"} &middot; {row.employee_name} &middot; by {row.actor_name}
          {recordId && <> &middot; <Link className="text-primary underline" to={`${application ? "/applications" : "/leads"}/${recordId}`}>Open record</Link></>}
        </p>;
      })}
      {!history.data?.items.length && <p className="text-sm text-textSecondary">No assignment events yet.</p>}
      <div className="flex items-center gap-3"><Button variant="secondary" disabled={historyPage === 1} onClick={() => setHistoryPage(historyPage - 1)}>Previous history</Button><span>Page {historyPage}</span><Button variant="secondary" disabled={historyPage * 20 >= (history.data?.total ?? 0)} onClick={() => setHistoryPage(historyPage + 1)}>Next history</Button></div>
    </section>
  </SimplePageLayout>;
}
