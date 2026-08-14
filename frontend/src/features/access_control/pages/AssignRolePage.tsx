import { useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { assignRole, listEmployeeRoles, removeRole, type EmployeeRoleAssignment } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";

export function AssignRolePage() {
  const { roleId } = useParams<{ roleId: string }>();
  const [employeeId, setEmployeeId] = useState("");
  const [assignments, setAssignments] = useState<EmployeeRoleAssignment[]>([]);
  const [lookedUpEmployeeId, setLookedUpEmployeeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  if (!roleId) return null;

  const onLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const roles = await listEmployeeRoles(employeeId.trim());
      setAssignments(roles);
      setLookedUpEmployeeId(employeeId.trim());
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const hasThisRole = assignments.some((a) => a.role_id === roleId);

  const onAssign = async () => {
    setError(null);
    setMessage(null);
    try {
      await assignRole(roleId, lookedUpEmployeeId);
      setMessage("Role assigned.");
      const roles = await listEmployeeRoles(lookedUpEmployeeId);
      setAssignments(roles);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onRemove = async () => {
    setError(null);
    setMessage(null);
    try {
      await removeRole(roleId, lookedUpEmployeeId);
      setMessage("Role removed.");
      const roles = await listEmployeeRoles(lookedUpEmployeeId);
      setAssignments(roles);
      setConfirmRemove(false);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Assign / Remove Role" backTo={`/roles/${roleId}`}>
      <ErrorBanner message={error} />
      {message && <p className="mb-4 text-sm text-success">{message}</p>}

      <form onSubmit={onLookup} className="max-w-md bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} />
        <SubmitButton>Look Up Employee's Roles</SubmitButton>
      </form>

      {lookedUpEmployeeId && (
        <div className="max-w-md bg-card border border-border rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-text/70 mb-3">Current roles for this employee</h3>
          {assignments.length === 0 ? (
            <p className="text-sm text-text/50 mb-4">No roles assigned yet.</p>
          ) : (
            <ul className="text-sm mb-4 list-disc list-inside">
              {assignments.map((a) => (
                <li key={a.id}>{a.role_name}</li>
              ))}
            </ul>
          )}

          {hasThisRole ? (
            <Button variant="secondary" size="sm" onClick={() => setConfirmRemove(true)}>
              Remove This Role
            </Button>
          ) : (
            <Button size="sm" onClick={onAssign}>
              Assign This Role
            </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmRemove}
        title="Remove Role"
        message="Remove this role from the employee? They will immediately lose the permissions it grants."
        confirmLabel="Remove Role"
        confirmVariant="danger"
        onConfirm={onRemove}
        onClose={() => setConfirmRemove(false)}
      />
    </SimplePageLayout>
  );
}
