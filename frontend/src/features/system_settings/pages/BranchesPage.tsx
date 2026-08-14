import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { Modal } from "@/components/overlays/Modal";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { EmptyState } from "@/components/layout/EmptyState";
import {
  activateBranch,
  type Address,
  type Branch,
  createBranch,
  deactivateBranch,
  listBranches,
  updateBranch,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

const EMPTY_ADDRESS: Address = { line1: "", line2: "", city: "", state: "", pincode: "" };

interface BranchFormState {
  name: string;
  code: string;
  phone: string;
  address: Address;
}

function toFormState(branch: Branch | null): BranchFormState {
  return {
    name: branch?.name ?? "",
    code: branch?.code ?? "",
    phone: branch?.phone ?? "",
    address: branch?.address ?? EMPTY_ADDRESS,
  };
}

function BranchFormModal({
  branch,
  onClose,
  onSaved,
}: {
  branch: Branch | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<BranchFormState>(() => toFormState(branch));
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const setAddress = (patch: Partial<Address>) => setForm((f) => ({ ...f, address: { ...f.address, ...patch } }));

  const hasAddress = Object.values(form.address).some((v) => v && v.trim());

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        code: form.code.trim(),
        phone: form.phone.trim() || undefined,
        address: hasAddress
          ? {
              line1: form.address.line1.trim(),
              line2: form.address.line2?.trim() || undefined,
              city: form.address.city.trim(),
              state: form.address.state.trim(),
              pincode: form.address.pincode.trim(),
            }
          : undefined,
      };
      if (branch) await updateBranch(branch.id, payload);
      else await createBranch(payload);
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={branch ? "Edit Branch" : "Add Branch"}
      size="md"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="branch-form" size="sm" loading={isSubmitting}>
            {branch ? "Save Changes" : "Add Branch"}
          </Button>
        </>
      }
    >
      <form id="branch-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Head Office" required />
          <FormField label="Code" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} placeholder="e.g. HO" required />
        </div>
        <FormField label="Phone (optional)" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />

        <p className="mb-2 mt-2 text-sm font-medium text-text">Address (optional)</p>
        <FormField
          label="Address Line 1"
          value={form.address.line1}
          onChange={(e) => setAddress({ line1: e.target.value })}
        />
        <FormField
          label="Address Line 2"
          value={form.address.line2 ?? ""}
          onChange={(e) => setAddress({ line2: e.target.value })}
        />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-3">
          <FormField label="City" value={form.address.city} onChange={(e) => setAddress({ city: e.target.value })} />
          <FormField label="State" value={form.address.state} onChange={(e) => setAddress({ state: e.target.value })} />
          <FormField label="Pincode" value={form.address.pincode} onChange={(e) => setAddress({ pincode: e.target.value })} />
        </div>
      </form>
    </Modal>
  );
}

export function BranchesPage() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [modalBranch, setModalBranch] = useState<Branch | null | "new">(null);

  const load = () => {
    listBranches()
      .then(setBranches)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onToggleStatus = async (branch: Branch) => {
    setError(null);
    try {
      if (branch.status === "active") await deactivateBranch(branch.id);
      else await activateBranch(branch.id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="Branches"
      subtitle="Manage branch offices and locations."
      actions={<Button size="sm" onClick={() => setModalBranch("new")}>+ Add Branch</Button>}
    >
      <ErrorBanner message={error} />

      {branches.length === 0 ? (
        <EmptyState
          icon="departments"
          title="No branches yet"
          description="Add your first branch office to get started."
          primaryAction={{ label: "+ Add Branch", onClick: () => setModalBranch("new") }}
        />
      ) : (
        <div className="overflow-x-auto rounded-card border border-border bg-card shadow-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Address</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {branches.map((branch) => (
                <tr key={branch.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3 font-medium text-text">{branch.name}</td>
                  <td className="px-4 py-3">{branch.code}</td>
                  <td className="px-4 py-3">{branch.phone || "—"}</td>
                  <td className="px-4 py-3">{branch.address ? `${branch.address.city}, ${branch.address.state}` : "—"}</td>
                  <td className="px-4 py-3 capitalize">{branch.status}</td>
                  <td className="px-4 py-3 text-right space-x-3">
                    <button type="button" className="text-primary hover:underline" onClick={() => setModalBranch(branch)}>
                      Edit
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(branch)}>
                      {branch.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalBranch && (
        <BranchFormModal
          branch={modalBranch === "new" ? null : modalBranch}
          onClose={() => setModalBranch(null)}
          onSaved={() => {
            setModalBranch(null);
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
