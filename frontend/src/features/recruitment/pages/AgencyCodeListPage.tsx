import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ActionButton } from "@/components/tables/ActionButton";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getAdvisor, listAdvisors, type AdvisorDetail, type AdvisorListItem } from "@/features/recruitment/api";
import { EditAdvisorModal } from "@/features/recruitment/components/EditAdvisorModal";
import { ADVISOR_CHANNEL_LABELS, ADVISOR_STATUS_LABELS } from "@/features/recruitment/labels";
import type { RecruitmentOutletContext } from "@/features/recruitment/pages/RecruitmentLayout";
import { getErrorMessage } from "@/shared/api/errors";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 15_000;

// The "Agency Code" recruitment tab IS the advisor roster seen from the recruitment side:
// every candidate who cleared the examination becomes an Advisor, and this is where staff
// assign the agency code / agent code / password and pick the QR vs Non QR type.
export function AgencyCodeListPage() {
  const { refreshCounts } = useOutletContext<RecruitmentOutletContext>();
  const { can } = usePermissions();
  const canEdit = can("insurance_management:recruitment", "edit");

  const [rows, setRows] = useState<AdvisorListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<AdvisorDetail | null>(null);

  const load = useCallback(() => {
    listAdvisors({ page, page_size: PAGE_SIZE })
      .then(({ data, pagination }) => {
        setRows(data);
        setTotal(pagination?.total ?? data.length);
        setError(null);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const openEdit = async (id: string) => {
    try {
      setEditing(await getAdvisor(id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onSaved = () => {
    load();
    refreshCounts();
  };

  return (
    <div className="p-4 lg:p-6">
      <div className="mb-4">
        <h1 className="text-xl font-bold text-text">Agency Code</h1>
        <p className="mt-0.5 text-sm text-textSecondary">
          Advisors created from cleared examinations. Assign the agency code, agent code and QR / Non QR type here.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      {!loading && rows.length === 0 ? (
        <EmptyState icon="user" title="No advisors yet." />
      ) : (
        <>
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Name</Th>
                <Th>Mobile</Th>
                <Th>Agency Code</Th>
                <Th>Agent Code</Th>
                <Th>Type</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <Td className="font-medium text-text">{row.full_name}</Td>
                  <Td>{row.mobile}</Td>
                  <Td className="text-textSecondary">{row.agency_code ?? "—"}</Td>
                  <Td className="text-textSecondary">{row.agent_code ?? "—"}</Td>
                  <Td>{ADVISOR_CHANNEL_LABELS[row.channel] ?? row.channel}</Td>
                  <Td>
                    <Badge tone={row.status === "active" ? "success" : "neutral"}>
                      {ADVISOR_STATUS_LABELS[row.status] ?? row.status}
                    </Badge>
                  </Td>
                  <Td>
                    <div className="flex justify-end gap-2">
                      <ActionButton to={`/insurance-management/advisors/${row.id}`} variant="view" />
                      {canEdit && <ActionButton variant="update" onClick={() => openEdit(row.id)} />}
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

      {editing && (
        <EditAdvisorModal advisor={editing} onClose={() => setEditing(null)} onSaved={onSaved} />
      )}
    </div>
  );
}
