import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  activateSecondaryOwner,
  deactivateSecondaryOwner,
  listOwnerAccounts,
  type OwnerAccountListItem,
} from "@/features/owner/api";
import { getErrorMessage } from "@/shared/api/errors";

const OWNER_TYPE_LABELS: Record<string, string> = { primary: "Primary Owner", secondary: "Secondary Owner" };
const OWNER_TYPE_CLASSES: Record<string, string> = { primary: "bg-primary/10 text-primary", secondary: "bg-text/10 text-text/70" };
const STATUS_CLASSES: Record<string, string> = { active: "bg-success/10 text-success", inactive: "bg-text/10 text-text/60" };

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function OwnerAccountListPage() {
  const [items, setItems] = useState<OwnerAccountListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    listOwnerAccounts()
      .then(setItems)
      .catch((err) => setLoadError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const toggleActive = async (owner: OwnerAccountListItem) => {
    setBusyId(owner.id);
    setMessage(null);
    setLoadError(null);
    try {
      if (owner.status === "active") {
        await deactivateSecondaryOwner(owner.id);
        setMessage(`${owner.full_name} deactivated.`);
      } else {
        await activateSecondaryOwner(owner.id);
        setMessage(`${owner.full_name} reactivated.`);
      }
      load();
    } catch (err) {
      setLoadError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <SimplePageLayout
      title="Owner Management"
      subtitle="Primary and Secondary Owner accounts for your company."
      actions={
        <Link to="/owner-accounts/new" className="rounded-lg bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light transition-colors">
          + Add Secondary Owner
        </Link>
      }
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {loadError && <p className="mb-4 text-sm text-danger">{loadError}</p>}

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Mobile</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Owner Type</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Created On</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon="shield-check"
                    title="No owner accounts found"
                    description="This shouldn't normally happen — your own Primary Owner account should always be listed here."
                  />
                </td>
              </tr>
            )}
            {items.map((owner) => (
              <tr key={owner.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">
                  {owner.owner_type === "secondary" ? (
                    <Link to={`/owner-accounts/${owner.id}/edit`} className="text-text hover:text-primary font-medium">{owner.full_name}</Link>
                  ) : (
                    <span className="text-text font-medium">{owner.full_name}</span>
                  )}
                </td>
                <td className="px-4 py-3">{owner.mobile}</td>
                <td className="px-4 py-3">{owner.email}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${OWNER_TYPE_CLASSES[owner.owner_type] ?? "bg-text/10 text-text/60"}`}>
                    {OWNER_TYPE_LABELS[owner.owner_type] ?? owner.owner_type}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium capitalize ${STATUS_CLASSES[owner.status] ?? "bg-text/10 text-text/60"}`}>
                    {owner.status}
                  </span>
                </td>
                <td className="px-4 py-3">{formatDate(owner.created_at)}</td>
                <td className="px-4 py-3">
                  {owner.owner_type === "secondary" && (
                    <div className="flex items-center justify-end gap-3 text-xs">
                      <Link to={`/owner-accounts/${owner.id}/edit`} className="text-primary hover:underline">Edit</Link>
                      <button type="button" disabled={busyId === owner.id} onClick={() => toggleActive(owner)} className="text-primary hover:underline disabled:opacity-40">
                        {owner.status === "active" ? "Deactivate" : "Reactivate"}
                      </button>
                    </div>
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
