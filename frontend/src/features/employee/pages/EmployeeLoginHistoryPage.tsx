import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getEmployeeLoginHistory, getOwnLoginHistory, type LoginHistoryEntry } from "@/features/employee/api";
import { getErrorMessage } from "@/features/employee/errors";

export function EmployeeLoginHistoryPage({ scope }: { scope: "self" | "owner" }) {
  const { employeeId } = useParams<{ employeeId: string }>();
  const [entries, setEntries] = useState<LoginHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetcher = scope === "self" ? getOwnLoginHistory() : getEmployeeLoginHistory(employeeId!);
    fetcher.then(setEntries).catch((err) => setError(getErrorMessage(err)));
  }, [scope, employeeId]);

  const backTo = scope === "self" ? "/profile" : `/employees/${employeeId}`;

  return (
    <SimplePageLayout title="Login History" backTo={backTo}>
      {error && <p className="text-sm text-danger mb-4">{error}</p>}
      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">IP Address</th>
              <th className="px-4 py-3">When</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-text/50">
                  No login history found.
                </td>
              </tr>
            )}
            {entries.map((e, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                <td className="px-4 py-3 capitalize">{e.event_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-3">{e.ip_address || "—"}</td>
                <td className="px-4 py-3">{new Date(e.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
