import { CaseListPage, type CaseListExtraColumn } from "@/components/pages/CaseListPage";
import { listLoanCases, type LoanCaseListItem } from "@/features/loan_management/api";
import { LOAN_STATUS_LABELS } from "@/features/loan_management/constants";

const EXTRA_COLUMNS: CaseListExtraColumn<LoanCaseListItem>[] = [
  { key: "selected_bank", label: "Selected Bank", render: (c) => c.selected_bank_name || "—" },
  { key: "approved_amount", label: "Approved Amount", render: (c) => (c.approved_amount != null ? `₹${c.approved_amount.toLocaleString("en-IN")}` : "—") },
];

export function LoanCaseListPage({ fixedStatus }: { fixedStatus?: string } = {}) {
  return (
    <CaseListPage
      icon="loan"
      entityLabel="Loan"
      itemLabel="loan case"
      detailBasePath="/loan-cases"
      statusLabels={LOAN_STATUS_LABELS}
      fixedStatus={fixedStatus}
      listFn={listLoanCases}
      extraColumns={EXTRA_COLUMNS}
      defaultDescription="Every loan application moving through underwriting to disbursement."
      reEligibleDescription="Rejected loan cases that become eligible to reapply after their cooldown period."
      emptyStateDescription="A loan case is created automatically once a customer's application is submitted."
    />
  );
}
