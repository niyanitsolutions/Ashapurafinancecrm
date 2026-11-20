import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { Modal } from "@/components/overlays/Modal";
import { apiRequest } from "@/shared/api/client";

export interface AssignmentResult { preview_id: string; preview: boolean; total: number; assigned: number; eligible: number; skipped: number; failed: number; results: { id: string; collection: string; status: string; reason: string }[] }

export function BulkAssignmentModal({ collection, ids, onClose, onDone }: { collection: "leads" | "applications"; ids: string[]; onClose: () => void; onDone: (result: AssignmentResult) => void }) {
  const [employees, setEmployees] = useState<{ id: string; name: string }[] | null>(null);
  const [employee, setEmployee] = useState("");
  const [reassign, setReassign] = useState(false);
  const [preview, setPreview] = useState<AssignmentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void apiRequest<{ id: string; name: string }[]>(`/leads/bulk-assignees?collection=${collection}`, { method: "POST", body: JSON.stringify({ ids }) })
      .then(rows => { if (active) setEmployees(rows); }).catch(err => { if (active) { setEmployees([]); setError(err instanceof Error ? err.message : "Unable to load eligible employees."); } });
    return () => { active = false; };
  }, [collection, ids]);
  const noun = collection === "leads" ? "Leads" : "Applications";
  async function submit() {
    if (busy || !employee) return;
    setBusy(true); setError(null);
    try {
      const result = await apiRequest<AssignmentResult>(collection === "leads" ? "/leads/bulk-assign" : "/applications/bulk-assign", {
        method: "POST", body: JSON.stringify({ ids, employee_id: employee, allow_reassignment: reassign, preview_id: preview?.preview_id }),
      });
      if (result.preview) setPreview(result); else onDone(result);
    } catch (err) { setError(err instanceof Error ? err.message : "Assignment failed. Refresh and review before retrying."); }
    finally { setBusy(false); }
  }
  return <Modal open title={`Assign selected ${noun.toLowerCase()}`} onClose={busy ? () => undefined : onClose}>
    <div className="space-y-4"><p>{ids.length} {noun} selected</p><ErrorBanner message={error} />
      {employees === null ? <p role="status">Loading eligible employees…</p> : <label className="grid gap-2 text-sm">Select Employee
        <select aria-label="Select Employee" className="rounded-lg border border-border bg-card p-3" value={employee} disabled={busy} onChange={event => { setEmployee(event.target.value); setPreview(null); }}>
          <option value="">Choose an eligible employee</option>{employees.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
        </select></label>}
      {employees?.length === 0 && <p className="text-sm text-textSecondary">No active employee has the required access for this selection. Review employee permissions or select records from one product.</p>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reassign} disabled={busy} onChange={event => { setReassign(event.target.checked); setPreview(null); }} />I explicitly authorize replacing existing assignments on the selected records.</label>
      {preview && <div className="rounded-lg border border-border p-3 text-sm"><p>{preview.eligible} ready · {preview.skipped} skipped · {preview.failed} failed</p>
        <ul className="mt-2 space-y-1">{preview.results.filter(row => row.status !== "eligible").map(row => <li key={row.id} className="break-all">{row.id}: {row.reason}</li>)}</ul>
        <p className="mt-3">Confirm assigning the eligible records to {employees?.find(row => row.id === employee)?.name}. Their existing lifecycle stages will be preserved.</p>
      </div>}
      <div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={busy} onClick={onClose}>Cancel</Button><Button disabled={busy || !employee || (preview !== null && preview.eligible === 0)} onClick={() => void submit()}>{busy ? "Processing…" : preview ? `Assign ${preview.eligible} ${noun}` : "Review assignments"}</Button></div>
    </div>
  </Modal>;
}
