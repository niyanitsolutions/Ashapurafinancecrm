import { CaseListPage } from "@/components/pages/CaseListPage";
import { listInsuranceCases } from "@/features/insurance_management/api";
import { INSURANCE_STATUS_LABELS } from "@/features/insurance_management/statusControl";

export function InsuranceCaseListPage({ fixedStatus }: { fixedStatus?: string } = {}) {
  const isReEligible = fixedStatus === "re_eligible";
  return (
    <CaseListPage
      icon="insurance"
      entityLabel="Insurance"
      itemLabel="policy lead"
      detailBasePath="/insurance-cases"
      statusLabels={INSURANCE_STATUS_LABELS}
      fixedStatus={fixedStatus}
      showFollowUp={isReEligible}
      listFn={listInsuranceCases}
      defaultDescription="Every insurance application moving from Fresh Lead through Policy Login to Policy Issued."
      reEligibleDescription="Rejected insurance cases that have become eligible to restart after their cooldown period."
      emptyStateDescription="A policy lead is created automatically once a customer's insurance application is submitted."
      deleteResourceKey="insurance_cases"
    />
  );
}
