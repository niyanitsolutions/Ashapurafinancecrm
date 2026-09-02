import { useState } from "react";
import { CaseListPage, type CaseListExtraColumn } from "@/components/pages/CaseListPage";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getLoanCase, listLoanCases, type LoanCaseDetail, type LoanCaseListItem } from "@/features/loan_management/api";
import { UpdateLoanCaseModal } from "@/features/loan_management/components/UpdateLoanCaseModal";
import { LOAN_STATUS_LABELS } from "@/features/loan_management/constants";

const TERMINAL_STATUSES = new Set(["disbursed", "rejected"]);

const EXTRA_COLUMNS: CaseListExtraColumn<LoanCaseListItem>[] = [
  { key: "selected_bank", label: "Selected Bank", render: (c) => c.selected_bank_name || "—" },
  { key: "approved_amount", label: "Approved Amount", render: (c) => (c.approved_amount != null ? `₹${c.approved_amount.toLocaleString("en-IN")}` : "—") },
];

// Decision #132: View opens the canonical read-only detail page at
// `/loan-management/cases/:id` — NOT the legacy `/loan-cases/:id` back-compat alias, so
// Loan Management's own UI never round-trips through the old route. Update opens the
// same stage-aware modal used from the detail page, directly from the list row — no
// separate update route/page.
export function LoanCaseListPage({ fixedStatus }: { fixedStatus?: string } = {}) {
  const { can } = usePermissions();
  const canEdit = can("loan_management:applications", "edit");
  // Disbursement is available to a case's `approve` holder OR its `edit` holder — mirrors
  // the backend's `require_any_permission(("approve", "edit"))` on POST /disburse.
  const canDisburse = can("loan_management:applications", "approve") || canEdit;
  const [updatingCase, setUpdatingCase] = useState<LoanCaseDetail | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const openUpdate = (row: LoanCaseListItem) => {
    getLoanCase(row.id).then(setUpdatingCase);
  };

  return (
    <>
      <CaseListPage
        refreshToken={refreshKey}
        icon="loan"
        entityLabel="Loan"
        itemLabel="loan case"
        detailBasePath="/loan-management/cases"
        statusLabels={LOAN_STATUS_LABELS}
        fixedStatus={fixedStatus}
        listFn={listLoanCases}
        extraColumns={EXTRA_COLUMNS}
        defaultDescription="Every loan application moving through underwriting to disbursement."
        reEligibleDescription="Rejected loan cases that become eligible to reapply after their cooldown period."
        emptyStateDescription="A loan case appears here once explicitly moved from Document Collection into Loan Management."
        onUpdate={canEdit || canDisburse ? openUpdate : undefined}
        canUpdateRow={(row) => !TERMINAL_STATUSES.has(row.current_status)}
        deleteResourceKey="loan_cases"
      />
      {updatingCase && (
        <UpdateLoanCaseModal
          caseId={updatingCase.id}
          loanCase={updatingCase}
          canEdit={canEdit}
          canDisburse={canDisburse}
          onClose={() => setUpdatingCase(null)}
          onUpdated={() => {
            getLoanCase(updatingCase.id).then(setUpdatingCase);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
    </>
  );
}
