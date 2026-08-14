import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { activateRole, deactivateRole, duplicateRole, getRole, type Role } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";

function DuplicateRoleModal({ onClose, onSaved }: { onClose: () => void; onSaved: (name: string) => void }) {
  const [name, setName] = useState("");
  return (
    <Modal
      open
      onClose={onClose}
      title="Duplicate Role"
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" disabled={!name.trim()} onClick={() => onSaved(name.trim())}>
            Duplicate
          </Button>
        </>
      }
    >
      <FormField label="New Role Name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
    </Modal>
  );
}

export function RoleDetailsPage() {
  const { roleId } = useParams<{ roleId: string }>();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmToggle, setConfirmToggle] = useState(false);
  const [isDuplicateOpen, setIsDuplicateOpen] = useState(false);

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
      setConfirmToggle(false);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onDuplicate = async (name: string) => {
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
      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 bg-card border border-border rounded-card shadow-card p-6">
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
          <Button variant="secondary" size="sm" className="w-full" onClick={() => setConfirmToggle(true)}>
            {role.status === "active" ? "Deactivate" : "Activate"}
          </Button>
          <Button variant="secondary" size="sm" className="w-full" onClick={() => setIsDuplicateOpen(true)}>
            Duplicate Role
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmToggle}
        title={role.status === "active" ? "Deactivate Role" : "Activate Role"}
        message={
          role.status === "active"
            ? `Deactivate "${role.name}"? Every employee currently assigned this role will lose the permissions it grants.`
            : `Activate "${role.name}"?`
        }
        confirmLabel={role.status === "active" ? "Deactivate" : "Activate"}
        confirmVariant={role.status === "active" ? "danger" : "primary"}
        onConfirm={onToggleStatus}
        onClose={() => setConfirmToggle(false)}
      />

      {isDuplicateOpen && (
        <DuplicateRoleModal
          onClose={() => setIsDuplicateOpen(false)}
          onSaved={(name) => {
            setIsDuplicateOpen(false);
            onDuplicate(name);
          }}
        />
      )}
    </SimplePageLayout>
  );
}
