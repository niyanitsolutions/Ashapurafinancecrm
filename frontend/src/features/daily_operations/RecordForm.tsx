import {useStatusOptions} from "./statusOptions";
import {LoanTypeField} from "./LoanTypeField";
import { useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { usePermissions } from "@/features/access_control/usePermissions";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";
import { istDateKey, todayISTDateString } from "@/shared/dateFormat";
import { FollowUpStatusField } from "./FollowUpStatusField";
import { BankMultiSelect } from "./BankMultiSelect";
import { recordBanks } from "./bankOptions";
import { EmployeeNameField } from "./EmployeeNameField";
import { base, businessTime, followStatuses, getLookups, issueStatuses, saveRecord, type Area, type Row } from "./api";

const dateValue = (value: unknown) => value ? /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? String(value) : istDateKey(String(value)) : "";

export function RecordForm({ area, record, onSaved, onCancel, onSavingChange }: {
  area: Area; record?: Row; onSaved: () => void; onCancel: () => void; onSavingChange?: (saving:boolean)=>void;
}) {
  const { userId } = useAuth();
  const { isOwner } = usePermissions();
  const statusOptions = useStatusOptions(area === "follow-ups", true);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const today = todayISTDateString();
    const defaults: Record<string, string> = {
      date: today, remarks_date: today, due_date: today, priority: "medium",
      status: area === "issues" ? "OPEN" : area === "progress" ? "Application login" : "FOLLOW UP PENDING",
    };
    for (const [key, value] of Object.entries(record ?? {})) {
      if (value != null && typeof value !== "object") defaults[key] = String(value);
    }
    for (const key of ["date", "remarks_date", "due_date", "reeligible_date", "login_date", "disbursed_at"]) {
      if (record && key in record) defaults[key] = dateValue(record[key]);
    }
    if (area === "sessions") {
      for (const key of ["login_at", "logout_at"]) {
        const date = record?.[key] ? new Date(String(record[key])) : null;
        defaults[key] = date ? `${istDateKey(String(record?.[key]))}T${date.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit" })}` : "";
      }
    }
    return defaults;
  });
  const [banks,setBanks]=useState(()=>recordBanks(record));
  const [linkSearch, setLinkSearch] = useState("");
  const lookup = useQuery({ queryKey: ["daily-lookups", userId, area, linkSearch], queryFn: () => getLookups(linkSearch,area === "progress"), enabled: area !== "sessions" });
  const employees = lookup.data?.employees ?? [];
  const defaultName = lookup.data?.self_name ?? employees.find(employee => employee.id === lookup.data?.self_id)?.name ?? (isOwner ? "Owner" : "");
  const selectedName = values.employee_name ?? employees.find(employee => employee.id === values.assigned_to)?.name ?? defaultName;
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingLock = useRef(false);
  const [submissionKey] = useState(() => crypto.randomUUID());
  const change = (key: string, value: string) => setValues(old => ({ ...old, [key]: value,
    ...(key === "date" && old.due_date === old.date ? { due_date: value } : {}),
    ...(key === "date" && old.remarks_date === old.date ? { remarks_date: value } : {}),
  }));
  const field = (key: string, label: string, required = false, type = "text", disabled = false) => (
    <FormField key={key} label={label} type={type} required={required} disabled={disabled}
      value={values[key] ?? ""} maxLength={1000} min={type === "number" ? 0 : key === "due_date" ? values.date : undefined}
      step={type === "number" ? "0.01" : undefined} onChange={event => change(key, event.target.value)} />
  );
  const linked = (area === "progress" && (!!values.case_id || !!values.lead_id)) || (area === "follow-ups" && Boolean(record?.working_key));
  const crmProgress = area === "progress" && !!values.case_id;
  const openFollowUp = followStatuses.slice(0, 2).includes(values.status);
  const statusLabel = statusOptions.data?.find(option => option.value === values.status)?.name ?? (values.status === record?.status ? String(record.status_display ?? values.status) : values.status);
  const reeligible = statusLabel.trim().toLowerCase().replaceAll("-", " ") === "re eligible";
  const showFollowUpDate = !reeligible && (openFollowUp || !followStatuses.includes(values.status));

  async function submit(event: FormEvent) {
    event.preventDefault(); if(savingLock.current) return; savingLock.current = true; setSaving(true);onSavingChange?.(true); setError(null);
    try {
      if (area === "sessions") {
        await apiRequest(`${base}/sessions/${record?.id}/correction`, {
          method: "POST", body: JSON.stringify({ login_at: `${values.login_at}:00+05:30`, logout_at: `${values.logout_at}:00+05:30`, reason: values.reason, version: record?.correction_version ?? 0 }),
        });
      } else {
        const selectedEmployee = employees.filter(employee => employee.name === selectedName);
        if (isOwner && selectedEmployee.length > 1) throw new Error("Several employees share this name. Select a unique employee name before saving.");
        const assignment = isOwner
          ? selectedEmployee.length === 1 ? selectedEmployee[0].id : record?.assigned_to ?? null
          : lookup.data?.self_id ?? record?.assigned_to ?? null;
        let payload: Record<string, unknown> = { date: values.date, employee_name: selectedName, assigned_to: assignment };
        if (area === "issues") {
          payload = { ...payload, inquiry: values.inquiry, priority: values.priority,
            status: values.status, resolution_notes: values.status === "RESOLVED" ? values.resolution_notes : "" };
        } else if (area === "follow-ups") {
          if(!banks.length)throw new Error("Select at least one Bank / NBFC.");
          if(reeligible && !values.reeligible_date)throw new Error("Re-Eligible Date is required.");
          payload = { ...payload, banks,
            customer_name: values.customer_name ?? "", customer_number: values.customer_number ?? "",
            loan_type: values.loan_type ?? "", status: values.status,
            reeligible_date: values.reeligible_date || null,
            remarks: values.remarks ?? "", remarks_date: values.remarks_date || values.date,
            next_action: values.next_action || values.remarks || "Follow up with customer",
            due_date: showFollowUpDate ? values.due_date || values.date : null,
            rejection_reason: values.status === "REJECTED WITH REASON" ? values.rejection_reason : "" };
        } else {
          payload = { ...payload, case_id: values.case_id || null,
            customer_name: values.customer_name ?? "", customer_number: values.customer_number ?? "",
            loan_type: values.loan_type ?? "", bank: values.bank ?? "", status: values.status,
            next_action: values.next_action ?? "", due_date: values.due_date || null, remarks: values.remarks ?? "",
            login_date: values.login_date || null, disbursed_at: values.disbursed_at || null,
            approved_amount: values.approved_amount ? Number(values.approved_amount) : null,
            disbursed_amount: values.disbursed_amount ? Number(values.disbursed_amount) : null };
        }
        if(area === "follow-ups" && !record) Object.assign(payload, { idempotency_key: submissionKey,
          separate_activity_reason: values.separate_activity_reason || "", identity_review_reason: values.identity_review_reason || "", review_customer_id: values.review_customer_id || null });
        if (record) payload.version = record.version ?? 0;
        await saveRecord(area, payload, record?.id);
      }
      onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save this row."); }
    finally { savingLock.current = false; setSaving(false);onSavingChange?.(false); }
  }

  const linkOptions = lookup.data?.cases ?? [];
  function linkRecord(id: string) {
    const selected = linkOptions.find(option => option.id === id);
    const isCase = id.startsWith("case:") || area === "progress";
    const canonicalId = id.replace(/^case:/, "");
    setValues(old => ({ ...old, lead_id: area === "follow-ups" && !isCase ? canonicalId : "", case_id: isCase ? canonicalId : "",
      customer_name: selected?.name ?? old.customer_name ?? "", customer_number: selected?.number ?? old.customer_number ?? "",
      bank: selected && "bank" in selected ? String(selected.bank) : old.bank ?? "" }));
  }

  return <form onSubmit={submit}>
    <ErrorBanner message={error} />
    {Boolean(record?.identity_warning) && <p role="alert" className="mb-3 text-sm text-orange-700">{String(record?.identity_warning)}</p>}
    {area === "follow-ups" && !record && <details className="mb-4 rounded-lg border border-border p-3"><summary>Duplicate and identity review</summary>
      <p className="my-2 text-sm text-textSecondary">Edit an existing follow-up to change it. For a legitimate separate activity on the same date, enter a reason. A retry keeps the same submission key.</p>
      {field("separate_activity_reason", "Reason for a separate same-day activity")}
      {isOwner && <><p className="my-2 text-sm">Verify identity before recording a distinct customer decision or linking a reviewed candidate. Use the read-only identity preview to inspect candidate IDs.</p>{field("identity_review_reason", "Owner identity review reason")}{field("review_customer_id", "Verified Customer ID (optional)")}</>}
    </details>}
    {area === "sessions" ? <>
      <p className="mb-3 text-sm text-textSecondary">Owner correction only. Original login records are retained. Times are in India time.</p>
      <p className="mb-3 text-sm">Original login: {businessTime(record?.original_login_at)} · Logout: {businessTime(record?.original_logout_at)}</p>
      <div className="grid sm:grid-cols-2 gap-x-4">{field("login_at", "Login time", true, "datetime-local")}{field("logout_at", "Logout time", true, "datetime-local")}</div>
      {field("reason", "Reason for correction", true)}
    </> : <>
      <div className="grid sm:grid-cols-2 gap-x-4">
        {field("date", "Date", true, "date")}
        <EmployeeNameField value={selectedName} options={employees} disabled={linked} onChange={name => change("employee_name", name)} />
        {area !== "issues" && <>
          {field("customer_name", "Customer name", !linked, "text", linked || Boolean(record?.customer_id))}
          {field("customer_number", "Customer number", !linked, "tel", linked || Boolean(record?.customer_id))}
          {linked?field("loan_type", "Loan type", false, "text", true):<LoanTypeField value={String(values.loan_type??"")} onChange={value=>setValues(prev=>({...prev,loan_type:value}))}/>}{area === "follow-ups"?<BankMultiSelect value={banks} onChange={setBanks}/>:field("bank", "Bank / NBFC", !crmProgress, "text", crmProgress)}
        </>}
      </div>
      {area === "issues" ? <>
        <TextareaField label="Inquiry or issue" required rows={3} maxLength={4000} value={values.inquiry ?? ""} onChange={event => change("inquiry", event.target.value)} />
        {!!record && <SelectField label="Status" value={values.status} options={issueStatuses.map(value => ({ value, label: value.replaceAll("_", " ") }))} onChange={event => change("status", event.target.value)} />}
        {values.status === "RESOLVED" && <TextareaField label="Resolution notes" rows={2} required value={values.resolution_notes ?? ""} onChange={event => change("resolution_notes", event.target.value)} />}
      </> : <>
      {crmProgress && <p className="mb-3 text-sm text-textSecondary">Edit the daily update here. Official approvals and amounts stay in Loan Management.</p>}
        {area === "follow-ups" ? <>
          <TextareaField label="Today's case status / remarks" rows={2} value={values.remarks ?? ""} maxLength={4000} placeholder="What happened today?" onChange={event => change("remarks", event.target.value)} />
          <div className="grid sm:grid-cols-2 gap-x-4">
            <FollowUpStatusField value={values.status} onChange={value=>change("status",value)} historicalValue={record?.status?String(record.status):undefined} historicalLabel={record?.status_display?String(record.status_display):undefined}/>
            {reeligible && field("reeligible_date", "Re-Eligible Date", true, "date")}
            {showFollowUpDate && field("due_date", "Next follow-up date", openFollowUp, "date")}
          </div>
          {values.status === "REJECTED WITH REASON" && field("rejection_reason", "Rejection reason", true)}
        </> : <>
          {field("status", "Today's case stage", true)}
          <div className="grid sm:grid-cols-2 gap-x-4">{field("next_action", "What's next?")}{field("due_date", "Next follow-up date", false, "date")}</div>
          <TextareaField label="Remarks" rows={2} value={values.remarks ?? ""} onChange={event => change("remarks", event.target.value)} />
        </>}
      </>}
      <details className="mb-4 rounded-lg border border-border p-3">
        <summary className="cursor-pointer text-sm font-medium">More details (optional)</summary>
        <div className="mt-3 grid sm:grid-cols-2 gap-x-4">
          {area === "follow-ups" && <>{field("remarks_date", "Remarks date", false, "date")}{field("next_action", "Next action")}</>}
          {area === "issues" && <SelectField label="Priority" value={values.priority} options={["low", "medium", "high", "urgent"].map(value => ({ value, label: value }))} onChange={event => change("priority", event.target.value)} />}
          {area === "progress" && <>
            {field("login_date", "Date of login", false, "date")}{field("approved_amount", "Approved loan amount", false, "number", crmProgress)}
            {field("disbursed_at", "Date of disbursement", false, "date", crmProgress)}{field("disbursed_amount", "Disbursed amount", false, "number", crmProgress)}
          </>}
        </div>
        {area === "progress" && <p className="text-xs text-textSecondary mb-3">Daily entries do not approve or disburse a loan. Official amounts are managed in Loan Management.</p>}
        {area === "progress" && !record && <>
          <FormField label="Find an existing CRM record (optional)" value={linkSearch} placeholder="Search customer name or case code" onChange={event => setLinkSearch(event.target.value)} />
          <SelectField label="Link existing CRM record" placeholder="Manual entry — no CRM link" value={values.case_id || ""}
            options={linkOptions.map(option => ({ value: option.id, label: [option.name, "bank" in option ? option.bank : "", option.code].filter(Boolean).join(" · ") }))}
            onChange={event => linkRecord(event.target.value)} />
        </>}
      </details>
    </>}
    <div className="flex justify-end gap-2 border-t border-border pt-4">
      <Button variant="secondary" onClick={onCancel}>Cancel</Button>
      <Button type="submit" loading={saving}>{record ? "Save changes" : "Save record"}</Button>
    </div>
  </form>;
}
