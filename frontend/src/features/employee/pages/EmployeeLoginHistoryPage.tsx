import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Pagination } from "@/components/tables/Pagination";
import { getEmployeeLoginHistory, getOwnLoginHistory, type LoginHistoryEntry } from "@/features/employee/api";
import { getErrorMessage } from "@/features/employee/errors";
import { formatISTDateTime } from "@/shared/dateFormat";

const PAGE_SIZE = 20;

export function EmployeeLoginHistoryPage({ scope }: { scope: "self" | "owner" }) {
  const { employeeId } = useParams<{ employeeId: string }>();
  const [entries, setEntries] = useState<LoginHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setIsLoading(true);
    const fetcher = scope === "self" ? getOwnLoginHistory() : getEmployeeLoginHistory(employeeId!);
    fetcher
      .then(setEntries)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [scope, employeeId]);

  const backTo = scope === "self" ? "/profile" : `/employees/${employeeId}`;
  const totalPages = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const pageItems = entries.slice((page - 1) * PAGE_SIZE, (page - 1) * PAGE_SIZE + PAGE_SIZE);

  return (
    <SimplePageLayout title="Login History" backTo={backTo}>
      <ErrorBanner message={error} />
      {isLoading ? (
        <p className="text-sm text-text/50">Loading…</p>
      ) : (
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
                  <td colSpan={3}>
                    <EmptyState icon="clock" title="No login history found" description="Login and logout events will appear here." />
                  </td>
                </tr>
              )}
              {pageItems.map((e, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 capitalize">{e.event_type.replace(/_/g, " ")}</td>
                  <td className="px-4 py-3">{e.ip_address || "—"}</td>
                  <td className="px-4 py-3">{formatISTDateTime(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {entries.length > 0 && (
            <div className="px-4 pb-4">
              <Pagination page={page} totalPages={totalPages} totalItems={entries.length} pageSize={PAGE_SIZE} itemLabel="entries" onPageChange={setPage} />
            </div>
          )}
        </div>
      )}
    </SimplePageLayout>
  );
}
