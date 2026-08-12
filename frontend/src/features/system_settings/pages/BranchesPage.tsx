import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  activateBranch,
  type Branch,
  createBranch,
  deactivateBranch,
  listBranches,
  updateBranch,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

// Branches have extra fields (code, phone, address) beyond the generic name+description
// shape, so this gets its own page rather than reusing NamedMasterDataPage. Address
// editing isn't exposed here (no UI need surfaced yet) — name/code/phone only.
export function BranchesPage() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    listBranches()
      .then(setBranches)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newCode.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await createBranch({ name: newName.trim(), code: newCode.trim(), phone: newPhone.trim() || undefined });
      setNewName("");
      setNewCode("");
      setNewPhone("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (branch: Branch) => {
    setEditingId(branch.id);
    setEditName(branch.name);
    setEditCode(branch.code);
    setEditPhone(branch.phone ?? "");
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await updateBranch(id, { name: editName.trim(), code: editCode.trim(), phone: editPhone.trim() || undefined });
      setEditingId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

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
    <SimplePageLayout title="Branches">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="mb-6 flex items-end gap-3 max-w-3xl">
        <div className="flex-1">
          <FormField label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Head Office" />
        </div>
        <div className="flex-1">
          <FormField label="Code" value={newCode} onChange={(e) => setNewCode(e.target.value)} placeholder="e.g. HO" />
        </div>
        <div className="flex-1">
          <FormField label="Phone (optional)" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
        </div>
        <div className="mb-4">
          <SubmitButton isSubmitting={isSubmitting}>Add</SubmitButton>
        </div>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {branches.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text/50">
                  No branches yet.
                </td>
              </tr>
            )}
            {branches.map((branch) =>
              editingId === branch.id ? (
                <tr key={branch.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2">
                    <input className="w-full rounded border border-border px-2 py-1" value={editName} onChange={(e) => setEditName(e.target.value)} />
                  </td>
                  <td className="px-4 py-2">
                    <input className="w-full rounded border border-border px-2 py-1" value={editCode} onChange={(e) => setEditCode(e.target.value)} />
                  </td>
                  <td className="px-4 py-2">
                    <input className="w-full rounded border border-border px-2 py-1" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} />
                  </td>
                  <td className="px-4 py-2 capitalize">{branch.status}</td>
                  <td className="px-4 py-2 text-right space-x-2">
                    <button type="button" className="text-primary hover:underline" onClick={() => onSaveEdit(branch.id)}>
                      Save
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={branch.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3">{branch.name}</td>
                  <td className="px-4 py-3">{branch.code}</td>
                  <td className="px-4 py-3">{branch.phone || "—"}</td>
                  <td className="px-4 py-3 capitalize">{branch.status}</td>
                  <td className="px-4 py-3 text-right space-x-3">
                    <button type="button" className="text-primary hover:underline" onClick={() => startEdit(branch)}>
                      Edit
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(branch)}>
                      {branch.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}
