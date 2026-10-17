import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/shared/api/errors";
import { ApiError } from "@/shared/api/client";
import { CallbackTimePreview } from "./CallbackTimePreview";
import { getContactPolicies, saveContactSuppression } from "./api";
import { changeCallback, createCallback, getCallbackHistory, getCallbacks, type CallbackEntity, type CallbackList, type CallbackRequest, type CallbackRow, type CallbackEvent } from "./callbackApi";

export function CallbacksPanel({ entityType, entityId }: { entityType: CallbackEntity; entityId: string }) {
  const { can, isOwner } = usePermissions(); const allowed = isOwner || can("voice_assistant:calls", "view");
  const [open, setOpen] = useState(false);
  if (!allowed) return null;
  return <section className="my-5 rounded-xl border bg-card p-4 space-y-3" aria-label="AI callback management">
    <div className="flex flex-wrap gap-3 items-center justify-between"><h2 className="font-semibold">AI callbacks</h2><Button variant="secondary" onClick={() => setOpen(!open)}>{open ? "Close callback manager" : "Schedule or review AI callbacks"}</Button></div>
    <p className="text-sm text-textSecondary">Customer time requests use the existing CRM tasks and preserve history. Live dialing remains blocked.</p>
    {open && <CallbackManager key={`${entityType}:${entityId}`} entityType={entityType} entityId={entityId} owner={isOwner} />}
  </section>;
}

function CallbackManager({ entityType, entityId, owner }: { entityType: CallbackEntity; entityId: string; owner: boolean }) {
  const [environment, setEnvironment] = useState<"test" | "production">("test"); const [page, setPage] = useState(1);
  const [data, setData] = useState<CallbackList | null>(null); const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [revision, setRevision] = useState(0);
  const [employee, setEmployee] = useState(""); const [local, setLocal] = useState(""); const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [fold, setFold] = useState(""); const [request, setRequest] = useState(""); const [rescheduling, setRescheduling] = useState<CallbackRow | null>(null);
  const [changeReason, setChangeReason] = useState(""); const submission = useRef<{ body: string; key: string } | null>(null);
  useEffect(() => {
    let active = true; setLoading(true); setError(null); setData(null);
    getCallbacks(entityType, entityId, environment, page).then(result => { if (active) setData(result); }).catch(err => { if (active) setError(getErrorMessage(err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [entityType, entityId, environment, page, revision]);
  async function work(operation: () => Promise<unknown>, refresh = true) {
    setBusy(true); setError(null);
    try { await operation(); if (refresh) setRevision(value => value + 1); }
    catch (err) { setError(getErrorMessage(err)); } finally { setBusy(false); }
  }
  function reset() { setLocal(""); setRequest(""); setRescheduling(null); setChangeReason(""); submission.current = null; }
  return <div className="space-y-4">
    <SelectField label="Callback environment" value={environment} disabled={busy} options={[{ value: "test", label: "Test — no real calls" }, { value: "production", label: "Production — dialing blocked" }]} onChange={e => { setEnvironment(e.target.value as typeof environment); setPage(1); reset(); }} />
    <ErrorBanner message={error} />
    {loading && <p role="status">Loading callbacks…</p>}
    <Button variant="ghost" disabled={busy || loading} onClick={() => setRevision(value => value + 1)}>Refresh callbacks</Button>
    {(data?.capabilities.create || (rescheduling && data?.capabilities.edit)) && <form className="space-y-3 border rounded-xl p-4" onSubmit={e => {
      e.preventDefault(); void work(async () => {
        if (rescheduling) {
          await changeCallback(rescheduling, { action: "reschedule", reason: changeReason, requested_local: local, timezone, ...(fold ? { dst_fold: Number(fold) } : {}) });
        } else {
          const body = { environment, entity_type: entityType, entity_id: entityId, assigned_to: owner ? employee : data.capabilities.current_employee_id ?? "", requested_local: local, timezone, customer_request: request, ...(fold ? { dst_fold: Number(fold) } : {}) };
          const serialized = JSON.stringify(body);
          if (!submission.current || submission.current.body !== serialized) submission.current = { body: serialized, key: crypto.randomUUID().replaceAll("-", "") };
          await createCallback({ ...body, idempotency_key: submission.current.key } as CallbackRequest);
        }
        reset();
      });
    }}>
      <fieldset disabled={busy} className="space-y-3">
      <h3 className="font-semibold">{rescheduling ? "Reschedule callback request" : "Record customer callback request"}</h3>
      <p className="text-sm">Record only the requested time and brief preference. Do not enter OTPs, passwords or financial details. Staff entry is an attestation; it does not establish caller identity or legal consent.</p>
      {!rescheduling && owner && <EmployeeSelect label="Callback supervisor" value={employee} onChange={setEmployee} activeOnly required />}
      {!rescheduling && <TextareaField label="Customer callback preference" required minLength={5} maxLength={500} value={request} onChange={e => setRequest(e.target.value)} />}
      {!rescheduling && <CallbackTimePreview request={request} timezone={timezone} disabled={busy} apply={value => { setLocal(value); setFold(""); }} />}
      {rescheduling && <FormField label="Reason for new requested time" required minLength={5} maxLength={160} value={changeReason} onChange={e => setChangeReason(e.target.value)} />}
      <div className="grid gap-3 sm:grid-cols-2"><FormField label="Requested local callback time" type="datetime-local" value={local} required onChange={e => setLocal(e.target.value)} /><FormField label="Callback timezone" required value={timezone} onChange={e => setTimezone(e.target.value)} /></div>
      <SelectField label="Daylight-saving occurrence, if ambiguous" value={fold} options={[{ value: "", label: "Require clarification if ambiguous" }, { value: "0", label: "First occurrence — customer confirmed" }, { value: "1", label: "Second occurrence — customer confirmed" }]} onChange={e => setFold(e.target.value)} />
      <Button type="submit" loading={busy}>{rescheduling ? "Save new time; confirmation required" : "Save callback request"}</Button>{rescheduling && <Button variant="secondary" onClick={reset}>Cancel rescheduling edit</Button>}
      </fieldset>
    </form>}
    {data?.items.length === 0 && <p>No callbacks recorded for this record in {environment}.</p>}
    {data?.items.map(row => <CallbackItem key={`${row.id}:${row.version}`} row={row} owner={owner} editable={data.capabilities.edit} busy={busy} work={work} onReschedule={() => { setRescheduling(row); setLocal(row.requested_local.slice(0, 16)); setTimezone(row.timezone); setChangeReason(""); setFold(""); }} />)}
    <div className="flex gap-2"><Button variant="secondary" disabled={busy || page === 1} onClick={() => setPage(page - 1)}>Previous callbacks</Button><Button variant="secondary" disabled={busy || page * 25 >= (data?.total ?? 0)} onClick={() => setPage(page + 1)}>Next callbacks</Button></div>
  </div>;
}

function CallbackItem({ row, owner, editable, busy, work, onReschedule }: { row: CallbackRow; owner: boolean; editable: boolean; busy: boolean; work: (operation: () => Promise<unknown>, refresh?: boolean) => Promise<void>; onReschedule: () => void }) {
  const [reason, setReason] = useState(""); const [confirmed, setConfirmed] = useState(false);
  const [history, setHistory] = useState<{ items: CallbackEvent[]; total: number } | null>(null); const [historyPage, setHistoryPage] = useState(1);
  const active = ["awaiting_confirmation", "confirmation_expired", "scheduled", "blocked"].includes(row.state);
  const date = (value: string, zone = row.timezone) => new Date(value).toLocaleString("en-IN", { timeZone: zone, timeZoneName: "shortOffset" });
  return <article className="border rounded-xl p-4 space-y-3">
    <h3 className="font-semibold">{row.state.replaceAll("_", " ")} · {date(row.due_at)} ({row.timezone})</h3>
    <p className="text-sm">Customer preference: {row.customer_request}</p><p className="text-sm">Staff-attested request · Calls placed: {row.calls_placed}</p>
    {row.blockers.length > 0 && <ul className="text-sm">{row.blockers.map(blocker => <li key={blocker}>Blocked: {blocker.replaceAll("_", " ")}</li>)}</ul>}
    {editable && active && <>
      <FormField label="Callback action reason" disabled={busy} minLength={5} maxLength={160} value={reason} onChange={e => setReason(e.target.value)} />
      {row.state === "awaiting_confirmation" && <label className="flex gap-2 items-start"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I have confirmed this exact date, time and timezone with the customer.</label>}
      <div className="flex flex-wrap gap-2">
        {row.state === "awaiting_confirmation" && <Button disabled={busy || !confirmed || reason.length < 5} onClick={() => void work(() => changeCallback(row, { action: "confirm", reason }))}>Confirm customer time</Button>}
        <Button variant="secondary" disabled={busy} onClick={onReschedule}>Reschedule callback</Button>
        <Button variant="danger" disabled={busy || reason.length < 5} onClick={() => void work(() => changeCallback(row, { action: "cancel", reason }))}>Cancel callback</Button>
        {row.state === "blocked" && <Button variant="secondary" disabled={busy || reason.length < 5} onClick={() => void work(() => changeCallback(row, { action: "retry_readiness", reason }))}>Recheck callback readiness</Button>}
        {owner && row.customer_id && <Button variant="danger" disabled={busy || reason.length < 5} onClick={() => void work(async () => {
          const customer = row.customer_id!; const policies = await getContactPolicies(customer);
          const current = policies.suppressions.find(policy => policy.scope === "global");
          await saveContactSuppression({ customer_id: customer, version: current?.version ?? 1, suppressed: true, reason });
          try { await changeCallback(row, { action: "cancel", reason: "Customer opt-out: global voice suppression saved" }); }
          catch { throw new ApiError("callback_changed_after_optout", "Global voice do-not-call was saved. Refresh to review the changed callback history."); }
        })}>Mark global voice do-not-call</Button>}
      </div>
    </>}
    <Button variant="ghost" disabled={busy} onClick={() => void work(async () => { setHistory(await getCallbackHistory(row.id, 1)); setHistoryPage(1); }, false)}>View callback history ({row.history_count})</Button>
    {history && <div><ul className="space-y-2 text-sm">{history.items.map((event, index) => <li key={`${event.at}:${index}`}><strong>{event.event.replaceAll("_", " ")}</strong> · {date(event.at)}{event.request && <p>{event.request}</p>}{event.reason && <p>{event.reason}</p>}{event.old_due_at && <p>Previous requested time: {date(event.old_due_at, event.old_timezone ?? row.timezone)} ({event.old_timezone ?? row.timezone})</p>}{event.new_due_at && <p>New requested time: {date(event.new_due_at, event.new_timezone ?? row.timezone)} ({event.new_timezone ?? row.timezone})</p>}</li>)}</ul><div className="flex gap-2 mt-3">{[historyPage - 1, historyPage + 1].map((target, index) => <Button key={index} variant="secondary" disabled={busy || target < 1 || target > Math.ceil(history.total / 25)} onClick={() => void work(async () => { setHistory(await getCallbackHistory(row.id, target)); setHistoryPage(target); }, false)}>{index === 0 ? "Newer history" : "Older history"}</Button>)}</div></div>}
  </article>;
}
