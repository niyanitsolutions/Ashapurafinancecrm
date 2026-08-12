import { useEffect, useState } from "react";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { useEmployeeNameMap } from "@/components/forms/useEmployeeNameMap";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  createTemporaryAccess,
  listPermissions,
  listTemporaryAccess,
  revokeTemporaryAccess,
  type Permission,
  type TemporaryAccess,
} from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";
import { friendlyPermissionLabel } from "@/features/access_control/permissionLabels";

export function TemporaryAccessPage() {
  const employeeNames = useEmployeeNameMap();
  const [items, setItems] = useState<TemporaryAccess[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [employeeId, setEmployeeId] = useState("");
  const [permissionId, setPermissionId] = useState("");
  const [actions, setActions] = useState("view");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("18:00");
  const [reason, setReason] = useState("");

  const load = () => {
    listTemporaryAccess().then(setItems).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(() => {
    load();
    listPermissions().then(setPermissions).catch(() => setPermissions([]));
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createTemporaryAccess({
        employee_id: employeeId,
        grants: [{ permission_id: permissionId, actions: actions.split(",").map((a) => a.trim()).filter(Boolean) }],
        start_date: startDate,
        end_date: endDate,
        start_time: startTime,
        end_time: endTime,
        reason,
      });
      setEmployeeId("");
      setReason("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onRevoke = async (id: string) => {
    setError(null);
    try {
      await revokeTemporaryAccess(id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Temporary Access">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Grant Temporary Access</h2>
        <div className="grid grid-cols-2 gap-x-4">
          <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} required />
          <SelectField
            label="Permission"
            placeholder="Select permission"
            value={permissionId}
            onChange={(e) => setPermissionId(e.target.value)}
            options={permissions.map((p) => ({ value: p.id, label: friendlyPermissionLabel(p) }))}
          />
          <FormField label="Actions (comma-separated)" value={actions} onChange={(e) => setActions(e.target.value)} />
          <FormField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
          <FormField label="Start date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
          <FormField label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
          <FormField label="Start time (daily)" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
          <FormField label="End time (daily)" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
        </div>
        <p className="text-xs text-text/50 mb-4">
          Access is granted only during this daily time window, each day within the date range.
        </p>
        <SubmitButton>Grant Access</SubmitButton>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Grants</th>
              <th className="px-4 py-3">Window</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-text/50">
                  No temporary access grants.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">{employeeNames[item.employee_id] ?? item.employee_id}</td>
                <td className="px-4 py-3">
                  {item.grants.map((g) => `${friendlyPermissionLabel(g)} (${g.actions.join(", ")})`).join("; ")}
                </td>
                <td className="px-4 py-3">
                  {item.start_date} → {item.end_date}, {item.start_time}–{item.end_time}
                </td>
                <td className="px-4 py-3">{item.reason}</td>
                <td className="px-4 py-3 capitalize">{item.status}</td>
                <td className="px-4 py-3">
                  {item.status === "active" && (
                    <button type="button" onClick={() => onRevoke(item.id)} className="text-danger hover:underline text-xs">
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
