import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { getErrorMessage } from "@/features/customer/errors";
import { listDisbursements, type DisbursementItem } from "@/features/loan_management/api";
import { loanProductsApi, type NamedMasterData } from "@/features/system_settings/api";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

type DatePreset = "this_week" | "this_month" | "this_quarter" | "this_year" | "custom";

const DATE_PRESETS: { value: DatePreset; label: string }[] = [
  { value: "this_week", label: "This Week" },
  { value: "this_month", label: "This Month" },
  { value: "this_quarter", label: "This Quarter" },
  { value: "this_year", label: "This Year" },
  { value: "custom", label: "Custom Date Range" },
];

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// Requirement 26 — resolves a preset to concrete [from, to] calendar dates entirely on
// the frontend (the backend only ever sees plain date_from/date_to, same shape as every
// other date-filtered report in this codebase); "This Month" is the default.
function presetRange(preset: DatePreset): { from: string; to: string } {
  const now = new Date();
  const today = toDateInput(now);
  if (preset === "this_week") {
    const day = now.getDay(); // 0 = Sunday
    const monday = new Date(now);
    monday.setDate(now.getDate() - ((day + 6) % 7));
    return { from: toDateInput(monday), to: today };
  }
  if (preset === "this_month") {
    return { from: toDateInput(new Date(now.getFullYear(), now.getMonth(), 1)), to: today };
  }
  if (preset === "this_quarter") {
    const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
    return { from: toDateInput(new Date(now.getFullYear(), quarterStartMonth, 1)), to: today };
  }
  if (preset === "this_year") {
    return { from: toDateInput(new Date(now.getFullYear(), 0, 1)), to: today };
  }
  return { from: today, to: today };
}

// Disbursements report (requirements 26-32) — date preset + product + search filters,
// a Total Disbursed Amount card, and a paginated table, ALL driven by one
// `listDisbursements(...)` call per filter change so the card/table/pagination can never
// disagree (the backend computes list + count + total from a single aggregation).
export function DisbursementsPage() {
  const [preset, setPreset] = useState<DatePreset>("this_month");
  const [customFrom, setCustomFrom] = useState(presetRange("this_month").from);
  const [customTo, setCustomTo] = useState(presetRange("this_month").to);
  const [productId, setProductId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [items, setItems] = useState<DisbursementItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalAmount, setTotalAmount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loanProductsApi.list().then(setProducts).catch(() => setProducts([]));
  }, []);

  const range = preset === "custom" ? { from: customFrom, to: customTo } : presetRange(preset);

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    listDisbursements({
      date_from: range.from || undefined, date_to: range.to || undefined, product_id: productId || undefined,
      search: search || undefined, page, page_size: pageSize,
    })
      .then((res) => {
        setItems(res.data?.items ?? []);
        setTotalCount(res.data?.total_count ?? 0);
        setTotalAmount(res.data?.total_amount ?? 0);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [range.from, range.to, productId, search, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const productLabel = productId ? (products.find((p) => p.id === productId)?.name ?? "Selected Product") : "All Loans";
  const presetLabel = DATE_PRESETS.find((p) => p.value === preset)?.label ?? "This Month";

  const clearFilters = () => {
    setPreset("this_month");
    setCustomFrom(presetRange("this_month").from);
    setCustomTo(presetRange("this_month").to);
    setProductId("");
    setSearch("");
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="p-6">
        <ErrorBanner message={error} />

        <div className="bg-card border border-border rounded-card shadow-card overflow-hidden mb-6">
          <div className="p-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon name="loan" className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-text">Disbursements</h1>
                <p className="text-sm text-textSecondary mt-0.5">All disbursed loan cases, filterable by date and product.</p>
              </div>
            </div>
          </div>

          <div className="px-6 pb-6 flex flex-wrap items-center gap-3">
            <select
              value={preset}
              onChange={(e) => {
                setPage(1);
                setPreset(e.target.value as DatePreset);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              {DATE_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>

            {preset === "custom" && (
              <>
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => {
                    setPage(1);
                    setCustomFrom(e.target.value);
                  }}
                  className="rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
                <span className="text-sm text-text/50">to</span>
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => {
                    setPage(1);
                    setCustomTo(e.target.value);
                  }}
                  className="rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </>
            )}

            <select
              value={productId}
              onChange={(e) => {
                setPage(1);
                setProductId(e.target.value);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              <option value="">All Loans</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>

            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Icon name="search" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-textSecondary" />
              <input
                type="text"
                placeholder="Case code / Customer…"
                value={search}
                onChange={(e) => {
                  setPage(1);
                  setSearch(e.target.value);
                }}
                className="w-full rounded-xl border border-border pl-9 pr-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            <button type="button" onClick={clearFilters} className="text-sm font-medium text-primary hover:underline">
              Clear Filters
            </button>
          </div>
        </div>

        <div className="mb-6 rounded-card bg-gradient-to-r from-primary to-primary-light px-6 py-6 text-white shadow-card">
          <p className="text-xs uppercase tracking-wide text-white/70">Total Disbursed Amount</p>
          <p className="text-3xl font-bold mt-1">₹{totalAmount.toLocaleString("en-IN")}</p>
          <p className="text-sm text-white/80 mt-1">
            {presetLabel} • {productLabel}
          </p>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableHeadRow>
                  <Th>Case Code</Th>
                  <Th>Customer</Th>
                  <Th>Product</Th>
                  <Th>Approved Amount</Th>
                  <Th>Disbursed Amount</Th>
                  <Th>Disbursed Date</Th>
                </TableHeadRow>
              </TableHead>
              <TableBody>
                {isLoading && (
                  <tr>
                    <Td colSpan={6} className="text-center text-text/50 py-6">
                      Loading…
                    </Td>
                  </tr>
                )}
                {!isLoading && items.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState
                        icon="loan"
                        title="No disbursements match your filters"
                        description="Try changing the date, product or search criteria."
                      />
                    </td>
                  </tr>
                )}
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <Td className="whitespace-nowrap">
                      <Link to={`/loan-management/cases/${item.id}`} className="text-primary font-medium hover:underline">
                        {item.case_code}
                      </Link>
                    </Td>
                    <Td>{item.customer_name || "—"}</Td>
                    <Td>{item.product_name}</Td>
                    <Td>{item.approved_amount != null ? `₹${item.approved_amount.toLocaleString("en-IN")}` : "—"}</Td>
                    <Td>{item.disbursed_amount != null ? `₹${item.disbursed_amount.toLocaleString("en-IN")}` : "—"}</Td>
                    <Td>{item.disbursed_at ? formatISTDateTime(item.disbursed_at) : "—"}</Td>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        <Pagination
          page={page}
          totalPages={totalPages}
          totalItems={totalCount}
          pageSize={pageSize}
          itemLabel="disbursements"
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
