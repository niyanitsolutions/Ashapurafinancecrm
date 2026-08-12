import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getEmployeeSessions, getOwnSessions, type SessionSummary } from "@/features/employee/api";
import { getErrorMessage } from "@/features/employee/errors";

export function EmployeeSessionsPage({ scope }: { scope: "self" | "owner" }) {
  const { employeeId } = useParams<{ employeeId: string }>();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetcher = scope === "self" ? getOwnSessions() : getEmployeeSessions(employeeId!);
    fetcher.then(setSessions).catch((err) => setError(getErrorMessage(err)));
  }, [scope, employeeId]);

  const backTo = scope === "self" ? "/profile" : `/employees/${employeeId}`;

  return (
    <SimplePageLayout title="Sessions" backTo={backTo}>
      {error && <p className="text-sm text-danger mb-4">{error}</p>}
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
                <td colSpan={6} className="px-4 py-6 text-center text-text/50">
                  No sessions found.
                </td>
              </tr>
            )}
            {sessions.map((s) => (
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
      </div>
    </SimplePageLayout>
  );
}
