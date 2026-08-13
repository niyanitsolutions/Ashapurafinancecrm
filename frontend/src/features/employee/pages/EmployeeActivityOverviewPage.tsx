import { useEffect, useState } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import { listEmployeeActivity, type EmployeeActivityEntry } from "@/features/employee/api";

const PAGE_SIZE = 20;

// Company-wide activity overview — reads the same `audit_logs` collection as an
// employee's own Login History tab (EmployeeDetailsPage), aggregated across every
// employee (see `GET /employees/activity`, owner-only).
export function EmployeeActivityOverviewPage() {
  const [items, setItems] = useState<EmployeeActivityEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [employeeId, setEmployeeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    listEmployeeActivity({
      page, page_size: PAGE_SIZE, employee_id: employeeId || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
    })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, employeeId, dateFrom, dateTo]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <SimplePageLayout title="Employee Activity" subtitle="Login and account activity across all employees.">
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-4 flex items-center gap-4">
        <input
          placeholder="Filter by Employee ID" value={employeeId}
          onChange={(e) => { setPage(1); setEmployeeId(e.target.value); }}
          className="rounded border border-border px-3 py-2 text-sm"
        />
        <input type="date" value={dateFrom} onChange={(e) => { setPage(1); setDateFrom(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm" />
        <span className="text-text/40 text-sm">to</span>
        <input type="date" value={dateTo} onChange={(e) => { setPage(1); setDateTo(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm" />
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Employee</th>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">IP Address</th>
              <th className="px-4 py-3">When</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <EmptyState icon="employees" title="No activity yet" description="Employee logins and account activity will show up here." />
                </td>
              </tr>
            )}
            {items.map((entry, idx) => (
              <tr key={`${entry.created_at}-${idx}`} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{entry.employee_name || "—"}</td>
                <td className="px-4 py-3 capitalize">{entry.event_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-3">{entry.ip_address || "—"}</td>
                <td className="px-4 py-3">{new Date(entry.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} events)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}
