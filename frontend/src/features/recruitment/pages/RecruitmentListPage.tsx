import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { Button } from "@/components/buttons/Button";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { ActionButton } from "@/components/tables/ActionButton";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { usePermissions } from "@/features/access_control/usePermissions";
import {
  getRecruitmentLead,
  listRecruitmentLeads,
  type RecruitmentLeadDetail,
  type RecruitmentLeadListItem,
} from "@/features/recruitment/api";
import { DocumentCollectionModal } from "@/features/recruitment/components/DocumentCollectionModal";
import { ExaminationModal } from "@/features/recruitment/components/ExaminationModal";
import { ExamFeeModal } from "@/features/recruitment/components/ExamFeeModal";
import { RecruitmentLeadModal } from "@/features/recruitment/components/RecruitmentLeadModal";
import { EXAM_LABELS, professionLabel } from "@/features/recruitment/labels";
import type { RecruitmentOutletContext } from "@/features/recruitment/pages/RecruitmentLayout";
import { getErrorMessage } from "@/shared/api/errors";
import { formatISTDate } from "@/shared/dateFormat";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 15_000;

type Variant = "fresh" | "bop" | "doc_collection" | "exam_fee_status" | "examination" | "re_examination" | "rejected";

const VARIANT_STAGE: Record<Variant, string> = {
  fresh: "fresh",
  bop: "bop",
  doc_collection: "doc_collection",
  exam_fee_status: "exam_fee_status",
  examination: "examination",
  re_examination: "re_examination",
  rejected: "rejected",
};

const META: Record<Variant, { title: string; description: string; empty: string }> = {
  fresh: {
    title: "Fresh Leads",
    description: "Newly captured recruitment leads waiting to be worked.",
    empty: "No fresh recruitment leads yet. Add one to get started.",
  },
  bop: {
    title: "BOP",
    description: "Recruitment leads currently in the Business Opportunity Presentation stage.",
    empty: "No recruitment leads in BOP.",
  },
  doc_collection: {
    title: "Doc Collection",
    description: "Candidates whose required documents are being collected. All documents must be uploaded before the candidate can move on.",
    empty: "No candidates in document collection.",
  },
  exam_fee_status: {
    title: "Exam Fee Status",
    description: "Candidates with documents complete, awaiting the examination fee to be recorded.",
    empty: "No candidates awaiting an exam fee.",
  },
  examination: {
    title: "Examination",
    description: "Candidates whose exam fee is recorded and who are ready for their examination.",
    empty: "No candidates awaiting examination.",
  },
  re_examination: {
    title: "Re-Examination",
    description: "Candidates who failed or were absent for a previous examination.",
    empty: "No candidates in re-examination.",
  },
  rejected: {
    title: "Rejected",
    description: "Recruitment leads that were rejected, kept for reporting and audit.",
    empty: "No rejected recruitment leads.",
  },
};

export function RecruitmentListPage({ variant }: { variant: Variant }) {
  const { refreshCounts } = useOutletContext<RecruitmentOutletContext>();
  const { can } = usePermissions();
  const canEdit = can("insurance_management:recruitment", "edit");
  const canCreate = can("insurance_management:recruitment", "create");

  const [rows, setRows] = useState<RecruitmentLeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [modal, setModal] = useState<
    | { kind: "create" }
    | { kind: "fresh" | "bop" | "documents" | "examfee" | "examination"; lead: RecruitmentLeadDetail }
    | null
  >(null);

  const meta = META[variant];

  const load = useCallback(() => {
    listRecruitmentLeads({ page, page_size: PAGE_SIZE, stage: VARIANT_STAGE[variant] })
      .then(({ data, pagination }) => {
        setRows(data);
        setTotal(pagination?.total ?? data.length);
        setError(null);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [page, variant]);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const openWithLead = async (id: string, kind: "fresh" | "bop" | "documents" | "examfee" | "examination") => {
    try {
      const lead = await getRecruitmentLead(id);
      setModal({ kind, lead });
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
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text">{meta.title}</h1>
          <p className="mt-0.5 text-sm text-textSecondary">{meta.description}</p>
        </div>
        {variant === "fresh" && canCreate && (
          <Button size="sm" onClick={() => setModal({ kind: "create" })}>
            + Add Lead
          </Button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {!loading && rows.length === 0 ? (
        <EmptyState icon="user" title={meta.empty} />
      ) : (
        <>
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Name</Th>
                <Th>Code</Th>
                <Th>Mobile</Th>
                <Th>Source</Th>
                <Th>Profession</Th>
                {variant === "rejected" ? <Th>Reason</Th> : <Th>Status</Th>}
                <Th>Created</Th>
                <Th className="text-right">Actions</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <Td className="font-medium text-text">{row.full_name}</Td>
                  <Td className="text-textSecondary">{row.recruitment_code}</Td>
                  <Td>{row.mobile}</Td>
                  <Td>{row.source_name}</Td>
                  <Td>{professionLabel(row.profession, row.other_profession)}</Td>
                  {variant === "rejected" ? (
                    <Td className="max-w-[16rem] truncate text-textSecondary">{row.rejected_reason ?? "—"}</Td>
                  ) : (
                    <Td>
                      {row.latest_examination_result ? (
                        <Badge tone={row.latest_examination_result === "pass" ? "success" : "danger"}>
                          {EXAM_LABELS[row.latest_examination_result]}
                        </Badge>
                      ) : row.documents_ready ? (
                        <Badge tone="info">Docs ready</Badge>
                      ) : (
                        <span className="text-2xs text-textSecondary">—</span>
                      )}
                    </Td>
                  )}
                  <Td className="text-textSecondary">{formatISTDate(row.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-2">
                      <ActionButton to={`/insurance-management/recruitment/${row.id}`} variant="view" />
                      {variant === "fresh" && canEdit && (
                        <ActionButton variant="update" onClick={() => openWithLead(row.id, "fresh")} />
                      )}
                      {variant === "bop" && canEdit && (
                        <ActionButton variant="update" onClick={() => openWithLead(row.id, "bop")} />
                      )}
                      {variant === "doc_collection" && canEdit && (
                        <ActionButton variant="edit" onClick={() => openWithLead(row.id, "documents")} />
                      )}
                      {variant === "exam_fee_status" && canEdit && (
                        <ActionButton variant="update" onClick={() => openWithLead(row.id, "examfee")} />
                      )}
                      {(variant === "examination" || variant === "re_examination") && canEdit && (
                        <ActionButton variant="update" onClick={() => openWithLead(row.id, "examination")} />
                      )}
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
            itemLabel="recruitment leads"
            onPageChange={setPage}
          />
        </>
      )}

      {modal?.kind === "create" && (
        <RecruitmentLeadModal mode="create" lead={null} onClose={() => setModal(null)} onSaved={onSaved} />
      )}
      {(modal?.kind === "fresh" || modal?.kind === "bop") && (
        <RecruitmentLeadModal mode={modal.kind} lead={modal.lead} onClose={() => setModal(null)} onSaved={onSaved} />
      )}
      {modal?.kind === "documents" && (
        <DocumentCollectionModal lead={modal.lead} onClose={() => setModal(null)} onSaved={onSaved} />
      )}
      {modal?.kind === "examfee" && (
        <ExamFeeModal lead={modal.lead} onClose={() => setModal(null)} onSaved={onSaved} />
      )}
      {modal?.kind === "examination" && (
        <ExaminationModal lead={modal.lead} onClose={() => setModal(null)} onSaved={onSaved} />
      )}
    </div>
  );
}
