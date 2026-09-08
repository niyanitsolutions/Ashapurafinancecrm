import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { CaseListPage } from "@/components/pages/CaseListPage";
import { usePermissions } from "@/features/access_control/usePermissions";
import { AddInsuranceLeadModal } from "@/features/insurance_management/components/AddInsuranceLeadModal";
import { listInsuranceCases } from "@/features/insurance_management/api";
import { INSURANCE_STATUS_LABELS } from "@/features/insurance_management/statusControl";

export function InsuranceCaseListPage({ fixedStatus }: { fixedStatus?: string } = {}) {
  const isReEligible = fixedStatus === "re_eligible";
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canCreate = can("insurance_management:applications", "edit");
  const [showAdd, setShowAdd] = useState(false);

  return (
    <>
      {canCreate && (
        <div className="flex justify-end px-6 pt-6">
          <Button size="sm" onClick={() => setShowAdd(true)}>
            + Add Insurance Lead
          </Button>
        </div>
      )}
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
        emptyStateDescription="An insurance policy lead is created when a customer submits an application, or by staff via + Add Insurance Lead."
        deleteResourceKey="insurance_cases"
      />
      {showAdd && (
        <AddInsuranceLeadModal
          onClose={() => setShowAdd(false)}
          onCreated={(created) => {
            setShowAdd(false);
            navigate(`/insurance-cases/${created.id}`);
          }}
        />
      )}
    </>
  );
}
