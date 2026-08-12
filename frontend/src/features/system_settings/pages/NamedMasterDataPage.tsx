import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/system_settings/errors";

interface Item {
  id: string;
  name: string;
  description?: string | null;
  status: string;
}

interface NamedMasterDataApi<T extends Item> {
  list: () => Promise<T[]>;
  create: (name: string, description?: string) => Promise<T>;
  update: (id: string, payload: { name?: string; description?: string }) => Promise<T>;
  activate: (id: string) => Promise<T>;
  deactivate: (id: string) => Promise<T>;
}

// Generic list/create/edit/activate/deactivate screen for the master-data resources that
// are just name+description+status (Lead Sources, Loan Products, Insurance Products,
// Document Types, Departments, Designations) — one implementation instead of six
// near-identical copies. See docs/decisions/DECISIONS.md.
export function NamedMasterDataPage<T extends Item>({
  title,
  createPlaceholder,
  api,
}: {
  title: string;
  createPlaceholder: string;
  api: NamedMasterDataApi<T>;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    api
      .list()
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await api.create(newName.trim(), newDescription.trim() || undefined);
      setNewName("");
      setNewDescription("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (item: T) => {
    setEditingId(item.id);
    setEditName(item.name);
    setEditDescription(item.description ?? "");
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await api.update(id, { name: editName.trim(), description: editDescription.trim() || undefined });
      setEditingId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onToggleStatus = async (item: T) => {
    setError(null);
    try {
      if (item.status === "active") {
        await api.deactivate(item.id);
      } else {
        await api.activate(item.id);
      }
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title={title}>
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="mb-6 flex items-end gap-3 max-w-2xl">
        <div className="flex-1">
          <FormField label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={createPlaceholder} />
        </div>
        <div className="flex-1">
          <FormField label="Description (optional)" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
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
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-text/50">
                  Nothing here yet.
                </td>
              </tr>
            )}
            {items.map((item) =>
              editingId === item.id ? (
                <tr key={item.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2">
                    <input
                      className="w-full rounded border border-border px-2 py-1"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      className="w-full rounded border border-border px-2 py-1"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                    />
                  </td>
                  <td className="px-4 py-2 capitalize">{item.status}</td>
                  <td className="px-4 py-2 text-right space-x-2">
                    <button type="button" className="text-primary hover:underline" onClick={() => onSaveEdit(item.id)}>
                      Save
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3">{item.name}</td>
                  <td className="px-4 py-3">{item.description || "—"}</td>
                  <td className="px-4 py-3 capitalize">{item.status}</td>
                  <td className="px-4 py-3 text-right space-x-3">
                    <button type="button" className="text-primary hover:underline" onClick={() => startEdit(item)}>
                      Edit
                    </button>
                    <button type="button" className="text-text/60 hover:underline" onClick={() => onToggleStatus(item)}>
                      {item.status === "active" ? "Deactivate" : "Activate"}
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
