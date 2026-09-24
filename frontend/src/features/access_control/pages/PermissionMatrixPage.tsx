import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { createPermission, getRolePermissions, listPermissions, setRolePermissions, type Permission } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";
import { sanitizeGrantedActions } from "@/features/access_control/permissionHierarchy";
import { PermissionMatrixSection } from "@/features/employee/components/PermissionMatrixSection";
import { buildMatrixGrants, DENY_PREFIX, MODULE_DISABLED, MODULE_ENABLED } from "@/features/employee/permissionMatrix";

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
      const permissionById = new Map(allPermissions.map((permission) => [permission.id, permission]));
      const next: Record<string, Set<string>> = {};
      for (const grant of roleGrants) {
        const available = permissionById.get(grant.permission_id)?.actions ?? grant.granted_actions;
        const selected = sanitizeGrantedActions(grant.granted_actions, available);
        for (const action of grant.denied_actions ?? []) selected.add(`${DENY_PREFIX}${action}`);
        if (grant.module_enabled === true) selected.add(MODULE_ENABLED);
        if (grant.module_enabled === false) selected.add(MODULE_DISABLED);
        next[grant.permission_id] = selected;
      }
      setGrants(next);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleId]);

  if (!roleId) return null;

  const onSave = async () => {
    setError(null);
    setMessage(null);
    setIsSaving(true);
    try {
      await setRolePermissions(roleId, buildMatrixGrants(permissions, grants));
      setMessage("Permission matrix saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const onCreatePermission = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const actions = newActions.split(",").map((action) => action.trim()).filter(Boolean);
      await createPermission(newModule.trim(), newResource.trim(), actions);
      setNewModule("");
      setNewResource("");
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Permission Matrix" backTo={`/roles/${roleId}`} actions={<SubmitButton onClick={onSave} isSubmitting={isSaving}>Save Matrix</SubmitButton>}>
      <ErrorBanner message={error} />
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <div className="mb-6"><PermissionMatrixSection permissions={permissions} checked={grants} onChange={setGrants} /></div>
      <div className="max-w-xl rounded-card border border-border bg-card p-6 shadow-card">
        <h2 className="mb-3 text-sm font-semibold text-text/70">Add a new permission (module + resource)</h2>
        <form onSubmit={onCreatePermission} className="grid grid-cols-1 gap-x-3 sm:grid-cols-3 sm:items-end">
          <FormField label="Module" value={newModule} onChange={(event) => setNewModule(event.target.value)} placeholder="loan_management" />
          <FormField label="Resource" value={newResource} onChange={(event) => setNewResource(event.target.value)} placeholder="leads" />
          <FormField label="Actions (comma-separated)" value={newActions} onChange={(event) => setNewActions(event.target.value)} />
          <div className="sm:col-span-3"><SubmitButton>Add to Catalog</SubmitButton></div>
        </form>
      </div>
    </SimplePageLayout>
  );
}
