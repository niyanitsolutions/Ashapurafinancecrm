import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  type InsuranceProduct,
  type NamedMasterData,
  insuranceCategoriesApi,
  insuranceProductsApi,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

const INLINE_EDIT_INPUT_CLASSES =
  "w-full rounded-xl border border-border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";

// Insurance Policy Leads redesign — Insurance Products belong to an InsuranceCategory,
// so this page has a Category selector that the generic NamedMasterDataPage can't
// provide. Loan Products stay on the generic page.
export function InsuranceProductsPage() {
  const [items, setItems] = useState<InsuranceProduct[]>([]);
  const [categories, setCategories] = useState<NamedMasterData[]>([]);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCategoryId, setNewCategoryId] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategoryId, setEditCategoryId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const activeCategoryOptions = useMemo(
    () => categories.filter((c) => c.status === "active").map((c) => ({ value: c.id, label: c.name })),
    [categories],
  );

  const load = () => {
    Promise.all([insuranceProductsApi.list(), insuranceCategoriesApi.list()])
      .then(([products, cats]) => {
        setItems(products);
        setCategories(cats);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newCategoryId) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await insuranceProductsApi.create({
        name: newName.trim(),
        category_id: newCategoryId,
        description: newDescription.trim() || undefined,
      });
      setNewName("");
      setNewDescription("");
      setNewCategoryId("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (item: InsuranceProduct) => {
    setEditingId(item.id);
    setEditName(item.name);
    setEditDescription(item.description ?? "");
    setEditCategoryId(item.category_id ?? "");
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await insuranceProductsApi.update(id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        category_id: editCategoryId || undefined,
      });
      setEditingId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onToggleStatus = async (item: InsuranceProduct) => {
    setError(null);
    try {
      if (item.status === "active") {
        await insuranceProductsApi.deactivate(item.id);
      } else {
        await insuranceProductsApi.activate(item.id);
      }
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Insurance Products">
      <ErrorBanner message={error} />

      {activeCategoryOptions.length === 0 && (
        <p className="mb-4 text-sm text-textSecondary">
          Add an active Insurance Category first — every product must belong to one.
        </p>
      )}

      <form onSubmit={onCreate} className="mb-6 flex flex-wrap items-end gap-3 max-w-3xl">
        <div className="flex-1 min-w-[180px]">
          <FormField label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Family Health Plus" />
        </div>
        <div className="flex-1 min-w-[180px]">
          <SelectField
            label="Category"
            name="new-category"
            options={activeCategoryOptions}
            placeholder="Select a category"
            value={newCategoryId}
            onChange={(e) => setNewCategoryId(e.target.value)}
          />
        </div>
        <div className="flex-1 min-w-[180px]">
          <FormField label="Description (optional)" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
        </div>
        <div className="mb-4">
          <SubmitButton isSubmitting={isSubmitting} disabled={!newCategoryId}>
            Add
          </SubmitButton>
        </div>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon="insurance" title="Nothing here yet" description="Add the first product using the form above." />
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
                    <select
                      className={INLINE_EDIT_INPUT_CLASSES}
                      value={editCategoryId}
                      onChange={(e) => setEditCategoryId(e.target.value)}
                      aria-label="Category"
                    >
                      {activeCategoryOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
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
                  <td className="px-4 py-3">{item.category_name || "—"}</td>
                  <td className="px-4 py-3">{item.description || "—"}</td>
                  <td className="px-4 py-3 capitalize">{item.status}</td>
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
