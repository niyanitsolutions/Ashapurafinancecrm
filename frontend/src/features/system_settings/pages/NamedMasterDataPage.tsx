import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";

const INLINE_EDIT_INPUT_CLASSES =
  "w-full rounded-xl border border-border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";
import { getErrorMessage } from "@/features/system_settings/errors";

interface Item {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  supports_password?: boolean;
}

interface NamedMasterDataApi<T extends Item> {
  list: () => Promise<T[]>;
  create: (name: string, description?: string, supportsPassword?: boolean) => Promise<T>;
  update: (id: string, payload: { name?: string; description?: string; supports_password?: boolean }) => Promise<T>;
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
  showPasswordSupport = false,
}: {
  title: string;
  createPlaceholder: string;
  api: NamedMasterDataApi<T>;
  // Document Types only — "Bank Statement" etc. See DocumentType.supports_password's
  // own docstring for why this lives on the shared model/page rather than a
  // DocumentType-only fork of this component.
  showPasswordSupport?: boolean;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newSupportsPassword, setNewSupportsPassword] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSupportsPassword, setEditSupportsPassword] = useState(false);
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
      await api.create(newName.trim(), newDescription.trim() || undefined, showPasswordSupport ? newSupportsPassword : undefined);
      setNewName("");
      setNewDescription("");
      setNewSupportsPassword(false);
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
    setEditSupportsPassword(item.supports_password ?? false);
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await api.update(id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        supports_password: showPasswordSupport ? editSupportsPassword : undefined,
      });
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

      <form onSubmit={onCreate} className="mb-6 flex flex-wrap items-end gap-3 max-w-2xl">
        <div className="flex-1 min-w-[200px]">
          <FormField label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={createPlaceholder} />
        </div>
        <div className="flex-1 min-w-[200px]">
          <FormField label="Description (optional)" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
        </div>
        {showPasswordSupport && (
          <div className="mb-4">
            <CheckboxField
              label="Supports password-protected files"
              checked={newSupportsPassword}
              onChange={(e) => setNewSupportsPassword(e.target.checked)}
            />
          </div>
        )}
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
              {showPasswordSupport && <th className="px-4 py-3">Password Support</th>}
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={showPasswordSupport ? 5 : 4}>
                  <EmptyState icon="departments" title="Nothing here yet" description="Add the first entry using the form above." />
                </td>
              </tr>
            )}
            {items.map((item) =>
              editingId === item.id ? (
                <tr key={item.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2">
                    <input
                      className={INLINE_EDIT_INPUT_CLASSES}
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      aria-label="Name"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      className={INLINE_EDIT_INPUT_CLASSES}
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      aria-label="Description"
                    />
                  </td>
                  <td className="px-4 py-2 capitalize">{item.status}</td>
                  {showPasswordSupport && (
                    <td className="px-4 py-2">
                      <CheckboxField
                        label="Supports password"
                        checked={editSupportsPassword}
                        onChange={(e) => setEditSupportsPassword(e.target.checked)}
                      />
                    </td>
                  )}
                  <td className="px-4 py-2 text-right space-x-2 whitespace-nowrap">
                    <Button variant="ghost" size="sm" onClick={() => onSaveEdit(item.id)}>
                      Save
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>
                      Cancel
                    </Button>
                  </td>
                </tr>
              ) : (
                <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                  <td className="px-4 py-3">{item.name}</td>
                  <td className="px-4 py-3">{item.description || "—"}</td>
                  <td className="px-4 py-3 capitalize">{item.status}</td>
                  {showPasswordSupport && <td className="px-4 py-3">{item.supports_password ? "Yes" : "No"}</td>}
                  <td className="px-4 py-3 text-right space-x-3 whitespace-nowrap">
                    <Button variant="ghost" size="sm" onClick={() => startEdit(item)}>
                      Edit
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onToggleStatus(item)}>
                      {item.status === "active" ? "Deactivate" : "Activate"}
                    </Button>
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
