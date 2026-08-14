import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { createRole, listRoles, type Role } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";

export function RoleListPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    listRoles().then(setRoles).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await createRole(newName.trim());
      setNewName("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SimplePageLayout title="Roles">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="mb-6 flex items-end gap-3 max-w-lg">
        <div className="flex-1">
          <FormField label="New role name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Branch Manager" />
        </div>
        <div className="mb-4">
          <SubmitButton isSubmitting={isSubmitting}>Create Role</SubmitButton>
        </div>
      </form>

      {roles.length === 0 ? (
        <EmptyState icon="roles" title="No roles yet" description="Create your first role above to start granting permissions to employees." />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {roles.map((role) => (
                <tr key={role.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3">
                    <Link to={`/roles/${role.id}`} className="text-primary hover:underline">
                      {role.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{role.description || "—"}</td>
                  <td className="px-4 py-3 capitalize">{role.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SimplePageLayout>
  );
}
