import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import {
  listBin,
  listDeletableResources,
  restoreRecord,
  type BinEntry,
  type DeletableResource,
} from "@/features/bin/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDate } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

// Centralized Bin (Owner-only — route-guarded by RequireOwner, and every /bin API call
// is Owner-gated server-side). Lists every soft-deleted business record with its module,
// stage, who deleted it and when, and its automatic permanent-deletion date (30 days
// after deletion). Restore returns the record — with all its data and relationships —
// to its module's normal lists.

export function BinPage() {
  const [entries, setEntries] = useState<BinEntry[]>([]);
  const [resources, setResources] = useState<DeletableResource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [moduleFilter, setModuleFilter] = useState("");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<BinEntry | null>(null);

  useEffect(() => {
    listDeletableResources()
      .then(setResources)
      .catch(() => setResources([]));
  }, []);

  const load = () => {
    setIsLoading(true);
    listBin({ page, page_size: pageSize, module: moduleFilter || undefined, search: search || undefined })
      .then((res) => {
        setEntries(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, pageSize, moduleFilter, search]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const moduleLabels = useMemo(() => new Map(resources.map((r) => [r.key, r.module_label])), [resources]);

  const doRestore = async () => {
    if (!restoring) return;
    try {
      await restoreRecord(restoring.id);
      setRestoring(null);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
      setRestoring(null);
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <ErrorBanner message={error} />

      <div className="bg-card border border-border rounded-card shadow-card overflow-hidden">
        <div className="p-6 flex items-start gap-3.5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-danger/10 text-danger">
            <Icon name="trash" className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-bold text-text">Bin</h1>
            <p className="text-sm text-textSecondary mt-0.5">
              Deleted records are kept here for 30 days, then permanently removed automatically.
            </p>
          </div>
        </div>

        <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px] max-w-sm">
            <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-textSecondary" />
            <input
              type="text"
              placeholder="Search by code or name…"
              value={search}
              onChange={(e) => {
                setPage(1);
                setSearch(e.target.value);
              }}
              className="w-full rounded-xl border border-border pl-9 pr-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <select
            value={moduleFilter}
            onChange={(e) => {
              setPage(1);
              setModuleFilter(e.target.value);
            }}
            className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          >
            <option value="">All Modules</option>
            {resources.map((r) => (
              <option key={r.key} value={r.key}>
                {r.module_label}
              </option>
            ))}
          </select>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Record</Th>
                <Th>Module</Th>
                <Th>Stage</Th>
                <Th>Deleted By</Th>
                <Th>Deleted On</Th>
                <Th>Permanent Delete</Th>
                <Th>Actions</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {isLoading && (
                <tr>
                  <Td colSpan={7} className="text-center text-text/50 py-6">
                    Loading…
                  </Td>
                </tr>
              )}
              {!isLoading && entries.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState icon="trash" title="The Bin is empty" description="Deleted records will appear here." />
                  </td>
                </tr>
              )}
              {entries.map((e) => (
                <TableRow key={e.id}>
                  <Td>
                    <div className="font-medium text-text">{e.record_code ?? e.record_summary ?? e.document_id}</div>
                    {e.record_code && e.record_summary && <div className="text-xs text-textSecondary">{e.record_summary}</div>}
                  </Td>
                  <Td>{moduleLabels.get(e.resource_key) ?? e.module_label}</Td>
                  <Td>{e.stage_label ?? "—"}</Td>
                  <Td>{e.deleted_by_name ?? e.deleted_by}</Td>
                  <Td>{formatISTDate(e.deleted_at)}</Td>
                  <Td>{formatISTDate(e.purge_at)}</Td>
                  <Td>
                    <Button size="sm" variant="secondary" onClick={() => setRestoring(e)}>
                      Restore
                    </Button>
                  </Td>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Pagination
        page={page}
        totalPages={totalPages}
        totalItems={total}
        pageSize={pageSize}
        itemLabel="records"
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
      />

      <ConfirmDialog
        open={restoring !== null}
        title="Restore this record?"
        message={`${restoring?.record_code ?? restoring?.record_summary ?? "This record"} will be returned to ${
          restoring ? moduleLabels.get(restoring.resource_key) ?? restoring.module_label : "its module"
        } with all its data.`}
        confirmLabel="Restore"
        onConfirm={doRestore}
        onClose={() => setRestoring(null)}
      />
    </div>
  );
}
