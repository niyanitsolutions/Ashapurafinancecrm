import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ActionButton } from "@/components/tables/ActionButton";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import {
  getAdvisorCounts,
  listAdvisors,
  type AdvisorCounts,
  type AdvisorFilterKey,
  type AdvisorListItem,
} from "@/features/recruitment/api";
import { formatINR } from "@/features/recruitment/labels";
import type { AdvisorOutletContext } from "@/features/recruitment/pages/AdvisorsLayout";
import { getErrorMessage } from "@/shared/api/errors";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 15_000;

const FILTERS: { key: AdvisorFilterKey | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "individual", label: "Individual" },
  { key: "total_employees", label: "Total Employees" },
  { key: "active", label: "Active" },
  { key: "inactive", label: "Inactive" },
];

export function AdvisorListPage({ channel }: { channel: "qr" | "non_qr" }) {
  const { refreshCounts } = useOutletContext<AdvisorOutletContext>();
  const [filter, setFilter] = useState<AdvisorFilterKey | "all">("all");
  const [rows, setRows] = useState<AdvisorListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [counts, setCounts] = useState<AdvisorCounts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    listAdvisors({
      channel,
      page,
      page_size: PAGE_SIZE,
      filter_key: filter === "all" ? undefined : filter,
    })
      .then(({ data, pagination }) => {
        setRows(data);
        setTotal(pagination?.total ?? data.length);
        setError(null);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
    getAdvisorCounts(channel)
      .then(setCounts)
      .catch(() => undefined);
  }, [channel, page, filter]);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const countFor = (key: AdvisorFilterKey | "all") =>
    !counts ? undefined : key === "all" ? counts.total : counts[key];

  const selectFilter = (key: AdvisorFilterKey | "all") => {
    setFilter(key);
    setPage(1);
    refreshCounts();
  };

  return (
    <div className="p-4 lg:p-6">
      <div className="mb-3">
        <h1 className="text-xl font-bold text-text">{channel === "qr" ? "QR Advisors" : "Non QR Advisors"}</h1>
        <p className="mt-0.5 text-sm text-textSecondary">
          Advisors {channel === "qr" ? "with an agency code assigned" : "not yet assigned an agency code"}.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => selectFilter(f.key)}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
              filter === f.key ? "border-primary bg-primary/10 text-primary" : "border-border text-textSecondary hover:bg-background"
            }`}
          >
            {f.label}
            {countFor(f.key) !== undefined && (
              <span className="ml-1.5 rounded-full bg-text/10 px-1.5 py-0.5 text-2xs">{countFor(f.key)}</span>
            )}
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} />}

      {!loading && rows.length === 0 ? (
        <EmptyState icon="user" title="No advisors match this view." />
      ) : (
        <>
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Name</Th>
                <Th>Mobile</Th>
                <Th>No. of Policies</Th>
                <Th>Premium Amount</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <Td className="font-medium text-text">
                    {row.full_name}
                    {row.is_employee && <span className="ml-2 text-2xs text-textSecondary">(employee)</span>}
                  </Td>
                  <Td>{row.mobile}</Td>
                  <Td>{row.no_of_policies}</Td>
                  <Td>{formatINR(row.total_premium)}</Td>
                  <Td>
                    <Badge tone={row.status === "active" ? "success" : "neutral"}>{row.status}</Badge>
                  </Td>
                  <Td>
                    <div className="flex justify-end">
                      <ActionButton to={`/insurance-management/advisors/${row.id}`} variant="view" />
                    </div>
                  </Td>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Pagination
            page={page}
            totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
            totalItems={total}
            pageSize={PAGE_SIZE}
            itemLabel="advisors"
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
