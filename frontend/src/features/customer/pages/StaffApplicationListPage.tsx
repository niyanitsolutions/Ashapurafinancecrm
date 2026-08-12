import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ActionButton } from "@/components/tables/ActionButton";
import { StatusBadge } from "@/components/badges/Badge";
import { ColumnsMenu, type ColumnOption } from "@/components/tables/ColumnsMenu";
import { EmptyState } from "@/components/layout/EmptyState";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { useAuth } from "@/features/auth/useAuth";
import { listApplicationsStaff, type ApplicationListItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon } from "@/theme/icons";

const OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: "customer", label: "Customer" },
  { key: "product", label: "Product" },
  { key: "assigned_to", label: "Assigned To" },
  { key: "status", label: "Status" },
];

export function StaffApplicationListPage() {
  const { role } = useAuth();
  const [items, setItems] = useState<ApplicationListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [status, setStatus] = useState("");
  // Owner-only — the "Unassigned Applications" queue (see docs/decisions/DECISIONS.md
  // #053). Employees only ever see work assigned to them, so this toggle has no meaning
  // for that role and isn't shown to them.
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
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

  useEffect(() => {
    setIsLoading(true);
    listApplicationsStaff({ page, page_size: pageSize, status: status || undefined, unassigned_only: unassignedOnly || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, pageSize, status, unassignedOnly]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="min-h-screen bg-background">
      <div className="p-6">
        {error && <p className="mb-4 text-sm text-danger">{error}</p>}

        <div className="bg-card rounded-2xl shadow-card overflow-hidden">
          <div className="p-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon name="applications" className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-text">Customer Applications</h1>
                <p className="text-sm text-textSecondary mt-0.5">Every application a customer has started or submitted.</p>
              </div>
            </div>
          </div>

          <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
            <select
              value={status}
              onChange={(e) => {
                setPage(1);
                setStatus(e.target.value);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              <option value="">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="submitted">Submitted</option>
            </select>
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
                Unassigned Applications only
              </label>
            )}
            <div className="ml-auto">
              <ColumnsMenu columns={OPTIONAL_COLUMNS} visible={visibleColumns} onToggle={toggleColumn} />
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableHeadRow>
                  <Th>Code</Th>
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
                        icon="applications"
                        title={unassignedOnly ? "No unassigned applications" : "No applications found"}
                        description={
                          unassignedOnly
                            ? "Every application currently has an owner."
                            : status
                              ? "Try a different status, or clear the filter to see every application."
                              : "Applications appear here once a customer starts filling one out."
                        }
                        secondaryAction={status ? { label: "Clear filter", onClick: () => { setStatus(""); setPage(1); } } : undefined}
                      />
                    </td>
                  </tr>
                )}
                {items.map((app) => (
                  <TableRow key={app.id}>
                    <Td className="whitespace-nowrap">
                      <Link to={`/applications/${app.id}`} className="text-primary font-medium hover:underline">
                        {app.application_code}
                      </Link>
                    </Td>
                    {isVisible("customer") && <Td>{app.customer_name || "—"}</Td>}
                    {isVisible("product") && <Td>{app.product_name}</Td>}
                    {isVisible("assigned_to") && (
                      <Td className={app.assigned_to_name ? "text-text" : "text-textSecondary"}>{app.assigned_to_name || "Unassigned"}</Td>
                    )}
                    {isVisible("status") && (
                      <Td>
                        <StatusBadge status={app.status} />
                      </Td>
                    )}
                    <Td>
                      <ActionButton to={`/applications/${app.id}`} variant="view" />
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
          itemLabel="applications"
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </div>
    </div>
  );
}
