import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { activateRole, deactivateRole, duplicateRole, getRole, type Role } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";

export function RoleDetailsPage() {
  const { roleId } = useParams<{ roleId: string }>();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = () => {
    if (!roleId) return;
    getRole(roleId).then(setRole).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [roleId]);

  if (!roleId) return null;

  const onToggleStatus = async () => {
    if (!role) return;
    setError(null);
    try {
      await (role.status === "active" ? deactivateRole(roleId) : activateRole(roleId));
      setMessage(role.status === "active" ? "Role deactivated." : "Role activated.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onDuplicate = async () => {
    const name = window.prompt("New role name?");
    if (!name) return;
    setError(null);
    try {
      const copy = await duplicateRole(roleId, name);
      navigate(`/roles/${copy.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  if (!role) {
    return (
      <SimplePageLayout title="Role" backTo="/roles">
        {error ? <p className="text-sm text-danger">{error}</p> : <p className="text-sm text-text/50">Loading…</p>}
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout title={role.name} backTo="/roles">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 bg-card border border-border rounded-card shadow-card p-6">
          <div className="text-xs text-text/50">Status</div>
          <div className="text-sm capitalize mb-4">{role.status}</div>
          <div className="text-xs text-text/50">Description</div>
          <div className="text-sm">{role.description || "—"}</div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3">
          <h3 className="text-sm font-semibold text-text/70">Actions</h3>
          <Link to={`/roles/${roleId}/permissions`} className="block text-sm text-primary hover:underline">
            Permission Matrix
          </Link>
          <Link to={`/roles/${roleId}/assign`} className="block text-sm text-primary hover:underline">
            Assign / Remove Employees
          </Link>
          <button type="button" onClick={onToggleStatus} className="w-full text-left text-sm rounded border border-border px-3 py-2 hover:bg-background">
            {role.status === "active" ? "Deactivate" : "Activate"}
          </button>
          <button type="button" onClick={onDuplicate} className="w-full text-left text-sm rounded border border-border px-3 py-2 hover:bg-background">
            Duplicate Role
          </button>
        </div>
      </div>
    </SimplePageLayout>
  );
}
