import { CaseListPage } from "@/components/pages/CaseListPage";
import { listInsuranceCases } from "@/features/insurance_management/api";

const STATUS_LABELS: Record<string, string> = {
  application_submitted: "Application Submitted",
  documents_pending: "Documents Pending",
  underwriting: "Underwriting",
  medical_verification: "Medical Verification",
  additional_documents: "Additional Documents",
  premium_acceptance: "Premium Acceptance",
  policy_generation: "Policy Generation",
  policy_issued: "Policy Issued",
  on_hold: "On Hold",
  rejected: "Rejected",
};

export function InsuranceCaseListPage({ fixedStatus, reEligible }: { fixedStatus?: string; reEligible?: boolean } = {}) {
  return (
    <CaseListPage
      icon="insurance"
      entityLabel="Insurance"
      itemLabel="insurance case"
      detailBasePath="/insurance-cases"
      statusLabels={STATUS_LABELS}
      fixedStatus={fixedStatus}
      reEligible={reEligible}
      listFn={listInsuranceCases}
      defaultDescription="Every policy application moving through underwriting to issuance."
      reEligibleDescription="Rejected insurance cases that become eligible to reapply after their cooldown period."
      emptyStateDescription="An insurance case is created automatically once a customer's application is submitted."
    />
  );
}
