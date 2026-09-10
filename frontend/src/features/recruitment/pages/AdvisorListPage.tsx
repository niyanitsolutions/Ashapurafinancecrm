import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/badges/Badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ActionButton } from "@/components/tables/ActionButton";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { listAdvisors, PROFESSIONS, type AdvisorListItem } from "@/features/recruitment/api";
import {
  ADVISOR_CHANNEL_LABELS,
  ADVISOR_STATUS_LABELS,
  formatINR,
  PROFESSION_LABELS,
  professionLabel,
} from "@/features/recruitment/labels";
import { getErrorMessage } from "@/shared/api/errors";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 15_000;

// Profession, Type and Status are three separate, independently-combinable filters.
// Profession values are Fresh Leads' single source of truth (`PROFESSIONS`).
const PROFESSION_CHIPS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  ...PROFESSIONS.map((p) => ({ value: p, label: PROFESSION_LABELS[p] })),
];

export function AdvisorListPage() {
  const [profession, setProfession] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<AdvisorListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    listAdvisors({
      page,
      page_size: PAGE_SIZE,
      profession: profession || undefined,
      channel: (channel as "qr" | "non_qr") || undefined,
      status: (status as "active" | "inactive") || undefined,
    })
      .then(({ data, pagination }) => {
        setRows(data);
        setTotal(pagination?.total ?? data.length);
        setError(null);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [page, profession, channel, status]);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const pickProfession = (value: string) => {
    setProfession(value);
    setPage(1);
  };

  return (
    <div className="p-4 lg:p-6">
      <div className="mb-3">
        <h1 className="text-xl font-bold text-text">Advisors</h1>
        <p className="mt-0.5 text-sm text-textSecondary">
          Filter by Profession, Type (QR / Non QR) and Status — each independently.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {PROFESSION_CHIPS.map((chip) => (
          <button
            key={chip.value || "all"}
            type="button"
            onClick={() => pickProfession(chip.value)}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
              profession === chip.value
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-textSecondary hover:bg-background"
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-xs font-semibold text-textSecondary">
          Type
          <select
            aria-label="Type"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="">All</option>
            <option value="qr">QR</option>
            <option value="non_qr">Non QR</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs font-semibold text-textSecondary">
          Status
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-text focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
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
                <Th>Profession</Th>
                <Th>Type</Th>
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
                  <Td>{row.profession ? professionLabel(row.profession, row.other_profession) : "—"}</Td>
                  <Td>{ADVISOR_CHANNEL_LABELS[row.channel] ?? row.channel}</Td>
                  <Td>{row.no_of_policies}</Td>
                  <Td>{formatINR(row.total_premium)}</Td>
                  <Td>
                    <Badge tone={row.status === "active" ? "success" : "neutral"}>
                      {ADVISOR_STATUS_LABELS[row.status] ?? row.status}
                    </Badge>
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
