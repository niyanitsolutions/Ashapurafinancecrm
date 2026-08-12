import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ActionButton } from "@/components/tables/ActionButton";
import { Badge } from "@/components/badges/Badge";
import { ColumnsMenu, type ColumnOption } from "@/components/tables/ColumnsMenu";
import { EmptyState } from "@/components/layout/EmptyState";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { listCustomersStaff, type CustomerListItem } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { Icon } from "@/theme/icons";

const OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: "mobile", label: "Mobile" },
  { key: "email", label: "Email" },
  { key: "status", label: "Status" },
];

// Owner sees every Customer; an Employee only sees ones with an application assigned to
// them — enforced entirely server-side (decision 050), this page just renders whatever
// the API returns.
export function CustomerListPage() {
  const [items, setItems] = useState<CustomerListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [search, setSearch] = useState("");
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
    listCustomersStaff({ page, page_size: pageSize, search: search || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, pageSize, search]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="min-h-screen bg-background">
      <div className="p-6">
        {error && <p className="mb-4 text-sm text-danger">{error}</p>}

        <div className="bg-card rounded-2xl shadow-card overflow-hidden">
          <div className="p-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon name="customers" className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-text">Customers</h1>
                <p className="text-sm text-textSecondary mt-0.5">Everyone whose lead has converted into a customer record.</p>
              </div>
            </div>
          </div>

          <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[240px] max-w-sm">
              <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-textSecondary" />
              <input
                type="text"
                placeholder="Search by name, code, email, mobile…"
                value={search}
                onChange={(e) => {
                  setPage(1);
                  setSearch(e.target.value);
                }}
                className="w-full rounded-xl border border-border pl-9 pr-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
            <div className="ml-auto">
              <ColumnsMenu columns={OPTIONAL_COLUMNS} visible={visibleColumns} onToggle={toggleColumn} />
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableHeadRow>
                  <Th>Code</Th>
                  <Th>Name</Th>
                  {isVisible("mobile") && <Th>Mobile</Th>}
                  {isVisible("email") && <Th>Email</Th>}
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
                      {search ? (
                        <EmptyState
                          icon="search"
                          title="No customers match your search"
                          description="Try a different name, code, email, or mobile number."
                          secondaryAction={{ label: "Clear search", onClick: () => { setSearch(""); setPage(1); } }}
                        />
                      ) : (
                        <EmptyState
                          icon="customers"
                          title="No customers yet"
                          description="Customers are created automatically once a Lead converts into an application. Convert your first lead to see it here."
                          primaryAction={{ label: "Go to Leads", to: "/leads" }}
                        />
                      )}
                    </td>
                  </tr>
                )}
                {items.map((c) => (
                  <TableRow key={c.id}>
                    <Td className="whitespace-nowrap">
                      <Link to={`/customers/${c.id}`} className="text-primary font-medium hover:underline">
                        {c.customer_code}
                      </Link>
                    </Td>
                    <Td className="font-semibold text-text">{c.full_name}</Td>
                    {isVisible("mobile") && (
                      <Td>
                        <span className="inline-flex items-center gap-1.5 text-text">
                          <Icon name="phone" className="h-3.5 w-3.5 text-textSecondary" />
                          {c.mobile}
                        </span>
                      </Td>
                    )}
                    {isVisible("email") && <Td className={c.email ? "text-text" : "text-textSecondary"}>{c.email || "—"}</Td>}
                    {isVisible("status") && (
                      <Td>
                        <Badge tone={c.status === "active" ? "success" : "neutral"}>{c.status}</Badge>
                      </Td>
                    )}
                    <Td>
                      <ActionButton to={`/customers/${c.id}`} variant="view" />
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
          itemLabel="customers"
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
