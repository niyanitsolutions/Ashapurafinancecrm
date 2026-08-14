import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Pagination } from "@/components/tables/Pagination";
import { getEmployeeSessions, type SessionSummary } from "@/features/employee/api";
import { getErrorMessage } from "@/features/employee/errors";

const PAGE_SIZE = 20;

// Owner-viewing-an-employee's-sessions only — the self-service "my sessions" experience
// (with per-session Revoke + Logout All Other Devices) lives at
// features/auth/pages/SessionsPage.tsx (/profile/sessions), not here.
export function EmployeeSessionsPage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!employeeId) return;
    setIsLoading(true);
    getEmployeeSessions(employeeId)
      .then(setSessions)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [employeeId]);

  const totalPages = Math.max(1, Math.ceil(sessions.length / PAGE_SIZE));
  const pageItems = sessions.slice((page - 1) * PAGE_SIZE, (page - 1) * PAGE_SIZE + PAGE_SIZE);

  return (
    <SimplePageLayout title="Sessions" backTo={`/employees/${employeeId}`}>
      <ErrorBanner message={error} />
      {isLoading ? (
        <p className="text-sm text-text/50">Loading…</p>
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">Browser / OS</th>
                <th className="px-4 py-3">IP / Location</th>
                <th className="px-4 py-3">Login At</th>
                <th className="px-4 py-3">Last Activity</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.length === 0 && (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon="user" title="No sessions found" description="This employee has no recorded login sessions yet." />
                  </td>
                </tr>
              )}
              {pageItems.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">{s.device || "—"}</td>
                  <td className="px-4 py-3">
                    {s.browser || "—"} / {s.operating_system || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {s.ip_address || "—"}
                    {s.city || s.country ? ` (${[s.city, s.country].filter(Boolean).join(", ")})` : ""}
                  </td>
                  <td className="px-4 py-3">{new Date(s.login_at).toLocaleString()}</td>
                  <td className="px-4 py-3">{new Date(s.last_activity_at).toLocaleString()}</td>
                  <td className="px-4 py-3 capitalize">{s.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {sessions.length > 0 && (
            <div className="px-4 pb-4">
              <Pagination page={page} totalPages={totalPages} totalItems={sessions.length} pageSize={PAGE_SIZE} itemLabel="sessions" onPageChange={setPage} />
            </div>
          )}
        </div>
      )}
    </SimplePageLayout>
  );
}
