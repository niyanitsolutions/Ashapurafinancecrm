import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  createPermission,
  getRolePermissions,
  listPermissions,
  setRolePermissions,
  type Permission,
} from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";

// Rows = catalog entries (module:resource); columns = only the actions each entry
// declares as applicable (per the data-driven design — not every action applies to
// every resource).
export function PermissionMatrixPage() {
  const { roleId } = useParams<{ roleId: string }>();
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [grants, setGrants] = useState<Record<string, Set<string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [newModule, setNewModule] = useState("");
  const [newResource, setNewResource] = useState("");
  const [newActions, setNewActions] = useState("view,create,edit");

  const load = async () => {
    if (!roleId) return;
    try {
      const [allPermissions, roleGrants] = await Promise.all([listPermissions(), getRolePermissions(roleId)]);
      setPermissions(allPermissions);
      const grantMap: Record<string, Set<string>> = {};
      for (const g of roleGrants) grantMap[g.permission_id] = new Set(g.granted_actions);
      setGrants(grantMap);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleId]);

  if (!roleId) return null;

  const toggle = (permissionId: string, action: string) => {
    setGrants((prev) => {
      const current = new Set(prev[permissionId] ?? []);
      if (current.has(action)) current.delete(action);
      else current.add(action);
      return { ...prev, [permissionId]: current };
    });
  };

  const onSave = async () => {
    setError(null);
    setMessage(null);
    setIsSaving(true);
    try {
      const payload = Object.entries(grants)
        .filter(([, actions]) => actions.size > 0)
        .map(([permission_id, actions]) => ({ permission_id, granted_actions: Array.from(actions) }));
      await setRolePermissions(roleId, payload);
      setMessage("Permission matrix saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const onCreatePermission = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const actions = newActions.split(",").map((a) => a.trim()).filter(Boolean);
      await createPermission(newModule.trim(), newResource.trim(), actions);
      setNewModule("");
      setNewResource("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Permission Matrix" backTo={`/roles/${roleId}`} actions={<SubmitButton onClick={onSave} isSubmitting={isSaving}>Save Matrix</SubmitButton>}>
      <ErrorBanner message={error} />
      {message && <p className="mb-4 text-sm text-success">{message}</p>}

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto mb-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Module</th>
              <th className="px-4 py-3">Resource</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {permissions.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-text/50">
                  No permission catalog entries yet — add one below.
                </td>
              </tr>
            )}
            {permissions.map((p) => (
              <tr key={p.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3 font-medium">{p.module}</td>
                <td className="px-4 py-3">{p.resource}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-3">
                    {p.actions.map((action) => (
                      <label key={action} className="flex items-center gap-1.5 text-xs capitalize">
                        <input
                          type="checkbox"
                          checked={grants[p.id]?.has(action) ?? false}
                          onChange={() => toggle(p.id, action)}
                        />
                        {action}
                      </label>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="max-w-xl bg-card border border-border rounded-card shadow-card p-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Add a new permission (module + resource)</h2>
        <form onSubmit={onCreatePermission} className="grid grid-cols-3 gap-x-3 items-end">
          <FormField label="Module" value={newModule} onChange={(e) => setNewModule(e.target.value)} placeholder="loan_management" />
          <FormField label="Resource" value={newResource} onChange={(e) => setNewResource(e.target.value)} placeholder="leads" />
          <FormField label="Actions (comma-separated)" value={newActions} onChange={(e) => setNewActions(e.target.value)} />
          <div className="col-span-3">
            <SubmitButton>Add to Catalog</SubmitButton>
          </div>
        </form>
      </div>
    </SimplePageLayout>
  );
}
