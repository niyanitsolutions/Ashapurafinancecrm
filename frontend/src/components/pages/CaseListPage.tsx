import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ActionButton } from "@/components/tables/ActionButton";
import { StatusBadge } from "@/components/badges/Badge";
import { ColumnsMenu, type ColumnOption } from "@/components/tables/ColumnsMenu";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon, type IconName } from "@/theme/icons";

export interface CaseListItem {
  id: string;
  case_code: string;
  customer_name: string | null;
  product_name: string;
  assigned_to_name: string | null;
  current_status: string;
}

export interface CaseListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  unassigned_only?: boolean;
}

export interface CaseListResponse<T> {
  data: T[];
  pagination: { total: number } | null;
}

const OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: "customer", label: "Customer" },
  { key: "product", label: "Product" },
  { key: "assigned_to", label: "Assigned To" },
  { key: "status", label: "Status" },
];

// Loan Management and Insurance Management case lists are structurally identical
// (Case Code/Customer/Product/Assigned To/Status, a fixed-status tab or a free "All
// Statuses" filter, an owner-only "Unassigned Cases only" toggle, a Re-Eligible tab with
// no backend yet) — this one component drives both, parameterized by module-specific
// bits. Each real module wraps it in a ~15-line file (see LoanCaseListPage.tsx /
// InsuranceCaseListPage.tsx) that only supplies its own API call, status labels, icon,
// and detail route.
export function CaseListPage<T extends CaseListItem>({
  icon,
  entityLabel,
  detailBasePath,
  itemLabel,
  statusLabels,
  fixedStatus,
  reEligible,
  listFn,
  defaultDescription,
  reEligibleDescription,
  emptyStateDescription,
}: {
  icon: IconName;
  entityLabel: string;
  detailBasePath: string;
  itemLabel: string;
  statusLabels: Record<string, string>;
  fixedStatus?: string;
  reEligible?: boolean;
  listFn: (params: CaseListParams) => Promise<CaseListResponse<T>>;
  /** Shown in the empty state when there are no cases at all yet — phrased per-entity
   * ("A loan case…" / "An insurance case…") so it isn't grammatically auto-generated. */
  emptyStateDescription: string;
  defaultDescription: string;
  reEligibleDescription: string;
}) {
  const { role } = useAuth();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [search, setSearch] = useState("");
  // Deep-linkable from Dashboard widgets/sidebar (e.g. /loan-cases?status=disbursed) —
  // only used as the initial value, not synced back to the URL on change. A tab with a
  // fixedStatus (e.g. Disbursements) always wins over the URL and hides the dropdown,
  // since the tab itself communicates the filter.
  const [status, setStatus] = useState(() => fixedStatus ?? searchParams.get("status") ?? "");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(!reEligible);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => new Set(OPTIONAL_COLUMNS.map((c) => c.key)));
  const toggleColumn = (key: string) =>
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const isVisible = (key: string) => visibleColumns.has(key);
  const columnCount = 2 + OPTIONAL_COLUMNS.filter((c) => isVisible(c.key)).length;

  const hasCustomFilters = !fixedStatus && !reEligible;

  useEffect(() => {
    // Re-Eligible has no backend status/API yet (only a reminder job computes this
    // internally, nothing persisted or queryable) — render the same table shell
    // pre-empty rather than invent a filter value the backend doesn't support; swapping
    // this early-return for a real fetch is the only change needed once that capability
    // ships.
    if (reEligible) {
      setItems([]);
      setTotal(0);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    listFn({
      page,
      page_size: pageSize,
      search: search || undefined,
      status: status || undefined,
      unassigned_only: unassignedOnly || undefined,
    })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, pageSize, search, status, unassignedOnly, reEligible, listFn]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const title = reEligible ? "Re-Eligible Cases" : fixedStatus ? (statusLabels[fixedStatus] ?? `${entityLabel} Cases`) : `${entityLabel} Cases`;
  const description = reEligible
    ? reEligibleDescription
    : fixedStatus
      ? undefined
      : status
        ? `Filtered by status: ${statusLabels[status] ?? status}`
        : defaultDescription;

  const clearFilters = () => {
    setSearch("");
    setStatus("");
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="p-6">
        <ErrorBanner message={error} />

        <div className="bg-card border border-border rounded-card shadow-card overflow-hidden">
          <div className="p-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon name={icon} className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-text">{title}</h1>
                {description && <p className="text-sm text-textSecondary mt-0.5">{description}</p>}
              </div>
            </div>
          </div>

          {!reEligible && (
            <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[240px] max-w-sm">
                <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-textSecondary" />
                <input
                  type="text"
                  placeholder={`Search by ${itemLabel} code, customer…`}
                  value={search}
                  onChange={(e) => {
                    setPage(1);
                    setSearch(e.target.value);
                  }}
                  className="w-full rounded-xl border border-border pl-9 pr-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
              {hasCustomFilters && (
                <select
                  value={status}
                  onChange={(e) => {
                    setPage(1);
                    setStatus(e.target.value);
                  }}
                  className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                >
                  <option value="">All Statuses</option>
                  {Object.entries(statusLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
              {role === "owner" && (
                <label className="flex items-center gap-2 rounded-xl border border-border px-3.5 py-2.5 text-sm text-text cursor-pointer">
                  <input
                    type="checkbox"
                    checked={unassignedOnly}
                    onChange={(e) => {
                      setPage(1);
                      setUnassignedOnly(e.target.checked);
                    }}
                    className="accent-primary"
                  />
                  Unassigned Cases only
                </label>
              )}
              <div className="ml-auto">
                <ColumnsMenu columns={OPTIONAL_COLUMNS} visible={visibleColumns} onToggle={toggleColumn} />
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableHeadRow>
                  <Th>Case Code</Th>
                  {isVisible("customer") && <Th>Customer</Th>}
                  {isVisible("product") && <Th>Product</Th>}
                  {isVisible("assigned_to") && <Th>Assigned To</Th>}
                  {isVisible("status") && <Th>Status</Th>}
                  <Th>Actions</Th>
                </TableHeadRow>
              </TableHead>
              <TableBody>
                {isLoading && (
                  <tr>
                    <Td colSpan={columnCount} className="text-center text-text/50 py-6">
                      Loading…
                    </Td>
                  </tr>
                )}
                {!isLoading && items.length === 0 && (
                  <tr>
                    <td colSpan={columnCount}>
                      <EmptyState
                        icon={reEligible ? "re-eligible" : icon}
                        title={
                          reEligible
                            ? "No re-eligible cases available"
                            : unassignedOnly
                              ? `No unassigned ${entityLabel.toLowerCase()} cases`
                              : search || status
                                ? `No ${entityLabel.toLowerCase()} cases match your filters`
                                : `No ${entityLabel.toLowerCase()} cases yet`
                        }
                        description={
                          reEligible
                            ? reEligibleDescription
                            : unassignedOnly
                              ? `Every ${entityLabel.toLowerCase()} case currently has an owner.`
                              : search || status
                                ? "Try a different search term, or clear the filters to see every case."
                                : emptyStateDescription
                        }
                        secondaryAction={hasCustomFilters && (search || status) ? { label: "Clear filters", onClick: clearFilters } : undefined}
                      />
                    </td>
                  </tr>
                )}
                {items.map((c) => (
                  <TableRow key={c.id}>
                    <Td className="whitespace-nowrap">
                      <Link to={`${detailBasePath}/${c.id}`} className="text-primary font-medium hover:underline">
                        {c.case_code}
                      </Link>
                    </Td>
                    {isVisible("customer") && <Td>{c.customer_name || "—"}</Td>}
                    {isVisible("product") && <Td>{c.product_name}</Td>}
                    {isVisible("assigned_to") && <Td className={c.assigned_to_name ? "text-text" : "text-textSecondary"}>{c.assigned_to_name || "Unassigned"}</Td>}
                    {isVisible("status") && (
                      <Td>
                        <StatusBadge status={c.current_status} label={statusLabels[c.current_status]} />
                      </Td>
                    )}
                    <Td>
                      <ActionButton to={`${detailBasePath}/${c.id}`} variant="view" />
                    </Td>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {!reEligible && (
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={total}
            pageSize={pageSize}
            itemLabel="cases"
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        )}
      </div>
    </div>
  );
}
