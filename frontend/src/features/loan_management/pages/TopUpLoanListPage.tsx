import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { CaseListPage, type CaseListExtraColumn } from "@/components/pages/CaseListPage";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/features/customer/errors";
import { listLoanCases, moveTopUpToDocumentCollection, type LoanCaseListItem } from "@/features/loan_management/api";
import { TopUpSchedulingModal } from "@/features/loan_management/components/TopUpSchedulingModal";
import { LOAN_STATUS_LABELS } from "@/features/loan_management/constants";
import { formatISTDate } from "@/shared/dateFormat";

const EXTRA_COLUMNS: CaseListExtraColumn<LoanCaseListItem>[] = [
  { key: "approved_amount", label: "Approved Amount", render: (c) => (c.approved_amount != null ? `₹${c.approved_amount.toLocaleString("en-IN")}` : "—") },
  { key: "disbursed_amount", label: "Disbursed Amount", render: (c) => (c.disbursed_amount != null ? `₹${c.disbursed_amount.toLocaleString("en-IN")}` : "—") },
  { key: "disbursed_date", label: "Disbursed Date", render: (c) => (c.disbursed_at ? formatISTDate(c.disbursed_at) : "—") },
];

// Production add-on: cases the customer became eligible to Top Up (see backend
// LoanCaseService.list_cases' top_up_eligible branch — always a plain `disbursed` case
// underneath, never a new LoanStatus). Reuses the exact same list/table component and
// column shape the Disbursed tab's list uses (`CaseListPage` + LoanCaseListItem), per
// spec — only the query filter and the row actions differ.
export function TopUpLoanListPage() {
  const { can } = usePermissions();
  const canEdit = can("loan_management:applications", "edit");
  const [reschedulingCaseId, setReschedulingCaseId] = useState<string | null>(null);
  const [movingCaseId, setMovingCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const onMoveToDocumentCollection = async (caseId: string) => {
    setError(null);
    setMovingCaseId(caseId);
    try {
      await moveTopUpToDocumentCollection(caseId);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setMovingCaseId(null);
    }
  };

  return (
    <>
      {error && <p className="px-6 pt-4 text-sm text-danger">{error}</p>}
      <CaseListPage
        refreshToken={refreshKey}
        icon="loan"
        entityLabel="Loan"
        itemLabel="loan case"
        detailBasePath="/loan-management/cases"
        statusLabels={LOAN_STATUS_LABELS}
        fixedStatus="disbursed"
        titleOverride="Top Up Loan"
        descriptionOverride="Disbursed loans whose Top Up eligibility period has been reached and are ready for a new Top Up application."
        listFn={(params) => listLoanCases({ ...params, top_up_eligible: true })}
        extraColumns={EXTRA_COLUMNS}
        defaultDescription="Disbursed loans whose Top Up eligibility period has been reached and are ready for a new Top Up application."
        reEligibleDescription=""
        emptyStateDescription="A loan appears here once its Top Up eligibility period (scheduled from the Disbursed list) has been reached."
        rowActions={
          canEdit
            ? (row) => (
                <>
                  <Button size="sm" variant="danger" onClick={() => setReschedulingCaseId(row.id)}>
                    Rejected
                  </Button>
                  <Button size="sm" variant="secondary" loading={movingCaseId === row.id} onClick={() => onMoveToDocumentCollection(row.id)}>
                    Move to Document Collection
                  </Button>
                </>
              )
            : undefined
        }
      />
      {reschedulingCaseId && (
        <TopUpSchedulingModal
          caseId={reschedulingCaseId}
          onClose={() => setReschedulingCaseId(null)}
          onScheduled={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </>
  );
}
