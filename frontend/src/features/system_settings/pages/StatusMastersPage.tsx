import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";

const INLINE_EDIT_INPUT_CLASSES =
  "w-full rounded-xl border border-border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";
import {
  activateStatusMaster,
  createStatusMaster,
  deactivateStatusMaster,
  listStatusMasters,
  type StatusMaster,
  updateStatusMaster,
} from "@/features/system_settings/api";
import { getErrorMessage } from "@/features/system_settings/errors";

// `category` is free text (per decision 021's data-driven philosophy) — the Owner types
// it, e.g. "loan_status" / "insurance_status" / "customer_status". No real status values
// are seeded (decision — see docs/decisions/DECISIONS.md): pipelines are business logic
// the brief didn't specify, so the Owner defines them here.
export function StatusMastersPage() {
  const [items, setItems] = useState<StatusMaster[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newName, setNewName] = useState("");
  const [newSequence, setNewSequence] = useState("0");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editSequence, setEditSequence] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = () => {
    listStatusMasters(categoryFilter.trim() || undefined)
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [categoryFilter]);  

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCategory.trim() || !newName.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await createStatusMaster({ category: newCategory.trim(), name: newName.trim(), sequence: Number(newSequence) || 0 });
      setNewName("");
      setNewSequence("0");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (item: StatusMaster) => {
    setEditingId(item.id);
    setEditName(item.name);
    setEditSequence(String(item.sequence));
  };

  const onSaveEdit = async (id: string) => {
    setError(null);
    try {
      await updateStatusMaster(id, { name: editName.trim(), sequence: Number(editSequence) || 0 });
      setEditingId(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onToggleStatus = async (item: StatusMaster) => {
    setError(null);
    try {
      if (item.status === "active") await deactivateStatusMaster(item.id);
      else await activateStatusMaster(item.id);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Status Masters">
      <ErrorBanner message={error} />

      <div className="mb-4 max-w-xs">
        <FormField
          label="Filter by category"
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          placeholder="e.g. loan_status"
        />
      </div>

      <form onSubmit={onCreate} className="mb-6 flex flex-wrap items-end gap-3 max-w-3xl">
        <div className="flex-1 min-w-[160px]">
          <FormField label="Category" value={newCategory} onChange={(e) => setNewCategory(e.target.value)} placeholder="e.g. loan_status" />
        </div>
        <div className="flex-1 min-w-[160px]">
          <FormField label="Status name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Disbursed" />
        </div>
        <div className="w-32">
          <FormField label="Sequence" type="number" value={newSequence} onChange={(e) => setNewSequence(e.target.value)} />
        </div>
        <div className="mb-4">
          <SubmitButton isSubmitting={isSubmitting}>Add</SubmitButton>
        </div>
      </form>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Sequence</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon="settings" title="No status values yet" description="Add the first status using the form above." />
                </td>
              </tr>
            )}
            {items.map((item) =>
              editingId === item.id ? (
                <tr key={item.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2 text-text/60">{item.category}</td>
                  <td className="px-4 py-2">
                    <input className={INLINE_EDIT_INPUT_CLASSES} value={editName} onChange={(e) => setEditName(e.target.value)} aria-label="Status name" />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      className={`w-24 ${INLINE_EDIT_INPUT_CLASSES}`}
                      value={editSequence}
                      onChange={(e) => setEditSequence(e.target.value)}
                      aria-label="Sequence"
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
                  <td className="px-4 py-3 text-text/60">{item.category}</td>
                  <td className="px-4 py-3">{item.name}</td>
                  <td className="px-4 py-3">{item.sequence}</td>
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
