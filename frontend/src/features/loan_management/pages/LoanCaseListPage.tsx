import { CaseListPage } from "@/components/pages/CaseListPage";
import { listLoanCases } from "@/features/loan_management/api";

const STATUS_LABELS: Record<string, string> = {
  new_customer: "New Customer",
  documents_pending: "Documents Pending",
  credit_evaluation: "Credit Evaluation",
  offer_acceptance: "Offer Acceptance",
  additional_documents: "Upload Additional Documents",
  esign_nach_kyc: "eSign / NACH / KYC",
  final_evaluation: "Final Evaluation",
  send_for_disbursement: "Send For Disbursement",
  disbursed: "Disbursed",
  on_hold: "On Hold",
  rejected: "Rejected",
};

export function LoanCaseListPage({ fixedStatus, reEligible }: { fixedStatus?: string; reEligible?: boolean } = {}) {
  return (
    <CaseListPage
      icon="loan"
      entityLabel="Loan"
      itemLabel="loan case"
      detailBasePath="/loan-cases"
      statusLabels={STATUS_LABELS}
      fixedStatus={fixedStatus}
      reEligible={reEligible}
      listFn={listLoanCases}
      defaultDescription="Every loan application moving through underwriting to disbursement."
      reEligibleDescription="Rejected loan cases that become eligible to reapply after their cooldown period."
      emptyStateDescription="A loan case is created automatically once a customer's application is submitted."
    />
  );
}
