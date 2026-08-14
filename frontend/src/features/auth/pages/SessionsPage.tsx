import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getOwnSessions, logoutAllOtherSessions, revokeSession, type SessionSummary } from "@/features/auth/api";
import { REFRESH_TOKEN_STORAGE_KEY } from "@/features/auth/context";
import { getErrorMessage } from "@/features/auth/errors";

// Self-service "Active Sessions" — every role's own devices (Owner/Employee/Referral
// Partner/Customer alike), with per-session revoke and "Logout All Other Devices". This
// is the role-agnostic equivalent of EmployeeSessionsPage, which stays Owner-only
// oversight of an *other* Employee's sessions, unchanged.
export function SessionsPage({ backTo }: { backTo: string }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false);

  const load = () => {
    getOwnSessions()
      .then(setSessions)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onRevoke = async (sessionId: string) => {
    setError(null);
    setBusyId(sessionId);
    try {
      await revokeSession(sessionId);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const onLogoutAllOther = async () => {
    setError(null);
    setIsLoggingOutAll(true);
    try {
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
      await logoutAllOtherSessions(refreshToken);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoggingOutAll(false);
    }
  };

  const activeCount = sessions.filter((s) => s.status === "active").length;

  return (
    <SimplePageLayout
      title="Active Sessions"
      backTo={backTo}
      actions={
        activeCount > 1 ? (
          <Button variant="ghost" size="sm" disabled={isLoggingOutAll} onClick={onLogoutAllOther}>
            {isLoggingOutAll ? "Logging out…" : "Logout All Other Devices"}
          </Button>
        ) : undefined
      }
    >
      <ErrorBanner message={error} />
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
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {sessions.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState icon="user" title="No sessions found" description="Your active and past login sessions will appear here." />
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
                <td className="px-4 py-3 text-right">
                  {s.status === "active" && (
                    <Button variant="ghost" size="sm" disabled={busyId === s.id} onClick={() => onRevoke(s.id)}>
                      Logout
                    </Button>
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
