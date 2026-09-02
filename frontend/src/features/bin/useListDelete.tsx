import { useCallback, useContext, useMemo, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { AuthContext } from "@/features/auth/authContext";
import { getErrorMessage } from "@/features/customer/errors";
import { bulkDeleteRecords, deleteRecord } from "@/features/bin/api";

// Shared Owner-only delete + bulk-delete controls for any list/table page. The backend
// (Depends(require_owner) on every /bin route) is the real gate — this only shows the
// affordances to an Owner and drives the confirmation dialog. Records are soft-deleted
// into the centralized Bin and auto-purged after 30 days.

export interface ListDelete {
  /** True only for an Owner — every list page hides its checkboxes + Delete buttons unless this is set. */
  enabled: boolean;
  selectedIds: Set<string>;
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
  toggleAll: (ids: string[]) => void;
  clear: () => void;
  /** Open the single-record confirm dialog. */
  requestDelete: (id: string) => void;
  /** Open the bulk confirm dialog for the current selection. */
  requestBulkDelete: () => void;
  /** Render inside the page — the confirmation dialog (null when nothing pending). */
  dialog: React.ReactNode;
  /** Render above the table when a selection exists. */
  bulkBar: React.ReactNode;
  error: string | null;
}

export function useListDelete(resourceKey: string, onChanged: () => void): ListDelete {
  // Delete is Owner-only and enforced server-side on every /bin route; the UI simply
  // hides the affordances for anyone else. Read the role straight from auth context (not
  // usePermissions / react-query) so this hook is usable from any list page without a
  // QueryClientProvider — and tolerate a missing provider (returns not-Owner) so it
  // never breaks a list page's own unit tests.
  const auth = useContext(AuthContext);
  const isOwner = auth?.role === "owner";
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clear = useCallback(() => setSelectedIds(new Set()), []);
  const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds]);

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id));
      return allSelected ? new Set() : new Set(ids);
    });
  }, []);

  const requestDelete = useCallback((id: string) => {
    setError(null);
    setPending([id]);
  }, []);

  const requestBulkDelete = useCallback(() => {
    setError(null);
    setPending([...selectedIds]);
  }, [selectedIds]);

  const confirm = useCallback(async () => {
    if (!pending) return;
    try {
      if (pending.length === 1) await deleteRecord(resourceKey, pending[0]);
      else await bulkDeleteRecords(resourceKey, pending);
      setPending(null);
      clear();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
      setPending(null);
    }
  }, [pending, resourceKey, clear, onChanged]);

  const count = pending?.length ?? 0;
  const dialog = pending ? (
    <ConfirmDialog
      open
      title={count > 1 ? `Delete ${count} records?` : "Delete this record?"}
      message={
        count > 1
          ? "These records will be moved to Bin and permanently deleted after 30 days."
          : "Are you sure you want to delete this record? It will be moved to Bin and permanently deleted after 30 days."
      }
      confirmLabel="Delete"
      confirmVariant="danger"
      onConfirm={confirm}
      onClose={() => setPending(null)}
    />
  ) : null;

  const bulkBar = useMemo(
    () =>
      isOwner && selectedIds.size > 0 ? (
        <div className="mb-3 flex items-center justify-between rounded-xl border border-danger/30 bg-danger/5 px-4 py-2.5 text-sm">
          <span className="font-medium text-text">{selectedIds.size} selected</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={clear}>
              Clear
            </Button>
            <Button size="sm" variant="danger" onClick={requestBulkDelete}>
              Delete
            </Button>
          </div>
        </div>
      ) : null,
    [isOwner, selectedIds.size, clear, requestBulkDelete],
  );

  return {
    enabled: isOwner,
    selectedIds,
    isSelected,
    toggle,
    toggleAll,
    clear,
    requestDelete,
    requestBulkDelete,
    dialog,
    bulkBar,
    error,
  };
}
