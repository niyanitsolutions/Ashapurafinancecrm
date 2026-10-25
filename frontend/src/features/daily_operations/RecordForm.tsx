import { useState, type FormEvent } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { usePermissions } from "@/features/access_control/usePermissions";
import { apiRequest } from "@/shared/api/client";
import { base, businessTime, followStatuses, issueStatuses, saveRecord, type Area, type Row } from "./api";

const today = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
export function RecordForm({ area, record, onSaved, onCancel }: { area: Area; record?: Row; onSaved: () => void; onCancel: () => void }) {
  const { can, isOwner } = usePermissions();
  const [values, setValues] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = { date: today(), remarks_date: today(), status: area === "issues" ? "OPEN" : "FOLLOW UP PENDING", priority: "medium" };
    for (const [key, value] of Object.entries(record ?? {})) if (value != null && typeof value !== "object") defaults[key] = String(value);
    if (area === "sessions") {
      defaults.login_at = String(record?.login_at ?? ""); defaults.logout_at = String(record?.logout_at ?? "");
    }
    return defaults;
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const change = (key: string, value: string) => setValues(old => ({ ...old, [key]: value }));
  const field = (key: string, label: string, required = false, type = "text", disabled = false) => <FormField key={key} label={label} type={type} required={required} disabled={disabled} value={values[key] ?? ""} maxLength={key === "remarks" || key === "inquiry" ? 4000 : 1000} onChange={e => change(key, e.target.value)} />;
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      if (area === "sessions") {
        await apiRequest(`${base}/sessions/${record?.id}/correction`, { method: "POST", body: JSON.stringify({ login_at: values.login_at, logout_at: values.logout_at, reason: values.reason, version: record?.correction_version ?? 0 }) });
      } else {
        const keys = area === "issues" ? ["date", "inquiry", "priority", "assigned_to", "status", "resolution_notes"] : ["date", "lead_id", "case_id", "bank", "status", "remarks", "remarks_date", "next_action", "due_date", "rejection_reason"];
        const payload: Record<string, unknown> = {};
        for (const key of keys) payload[key] = values[key] || (["case_id", "assigned_to", "due_date"].includes(key) ? null : "");
        if (area === "follow-ups") {
          if (!["FOLLOW UP PENDING", "NEXT FOLLOW UP"].includes(values.status)) payload.due_date = null;
          if (values.status !== "REJECTED WITH REASON") payload.rejection_reason = "";
        } else if (values.status !== "RESOLVED") payload.resolution_notes = "";
        if (record) payload.version = record.version;
        await saveRecord(area, payload, record?.id);
      }
      onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save record."); }
    finally { setSaving(false); }
  }
  const statuses = area === "issues" ? issueStatuses : followStatuses;
  return <form onSubmit={submit}>
    <ErrorBanner message={error} />
    {area === "sessions" ? <>
      <p className="mb-4 text-sm">Corrections preserve the original session. Enter ISO timestamps with a timezone, for example YYYY-MM-DDTHH:mm:ss+05:30. Recorded duration is not payroll attendance.</p>
      <p className="mb-4 text-sm">Original LOGIN TIME: {businessTime(record?.original_login_at)} · Original LOGOUT TIME: {businessTime(record?.original_logout_at)} · Correction version: {String(record?.correction_version ?? 0)}</p>
      {field("login_at", "LOGIN TIME", true)}{field("logout_at", "LOGOUT TIME", true)}{field("reason", "Correction reason", true)}
    </> : <>
      {field("date", "DATE", true, "date")}
      {area === "follow-ups" ? <>
        {field("lead_id", "LEAD ID (existing CRM ID)", true, "text", !!record)}
        {field("case_id", "LOAN CASE ID (required for DISBURSE)", values.status === "DISBURSE", "text", !!record?.case_id)}
        {field("bank", "BANK / NBFCs", true)}
        {field("remarks", "REMARKS")}{field("remarks_date", "REMARKS DATE", true, "date")}
      </> : <>
        {field("inquiry", "INQUIRY OR ISSUE", true)}
        <SelectField label="Priority" value={values.priority} options={["low", "medium", "high", "urgent"].map(value => ({ value, label: value }))} onChange={e => change("priority", e.target.value)} />
        {(isOwner || can("daily_operations:issues", "assign")) && field("assigned_to", "Assigned To (employee CRM ID)")}
      </>}
      <SelectField label={area === "issues" ? "Status" : "TODAY CASE STATUS"} value={values.status} options={statuses.filter(value => area !== "issues" || value !== "RESOLVED" || can("daily_operations:issues", "approve")).map(value => ({ value, label: value }))} onChange={e => change("status", e.target.value)} />
      {area === "follow-ups" && <>
        {field("next_action", "NEXT ACTION", ["FOLLOW UP PENDING", "NEXT FOLLOW UP"].includes(values.status))}
        {["FOLLOW UP PENDING", "NEXT FOLLOW UP"].includes(values.status) && field("due_date", "FOLLOW PENDING", true, "date")}
        {values.status === "REJECTED WITH REASON" && field("rejection_reason", "Rejection reason", true)}
        {values.status === "DISBURSE" && <p className="mb-4 text-sm">The linked case must already have a verified disbursement in Loan Management.</p>}
      </>}
      {area === "issues" && values.status === "RESOLVED" && field("resolution_notes", "Resolution Notes", true)}
    </>}
    <div className="flex gap-2"><Button type="submit" loading={saving}>{area === "sessions" ? "Save audited correction" : "Save"}</Button><Button variant="secondary" onClick={onCancel}>Cancel</Button></div>
  </form>;
}
