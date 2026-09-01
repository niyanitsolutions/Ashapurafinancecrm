import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { Modal } from "@/components/overlays/Modal";
import { updateAdvisor, type AdvisorDetail } from "@/features/recruitment/api";
import { getErrorMessage } from "@/shared/api/errors";

export function EditAdvisorModal({
  advisor,
  onClose,
  onSaved,
}: {
  advisor: AdvisorDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [agencyCode, setAgencyCode] = useState(advisor.agency_code ?? "");
  const [status, setStatus] = useState<"active" | "inactive">(advisor.status);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSave = async () => {
    setBusy(true);
    setError(null);
    try {
      await updateAdvisor(advisor.id, { agency_code: agencyCode.trim(), status });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Edit Advisor"
      description={`${advisor.advisor_code} — an agency code assigns the advisor to the QR channel`}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button size="sm" onClick={onSave} loading={busy}>
            Save
          </Button>
        </>
      }
    >
      {error && <ErrorBanner message={error} />}
      <FormField
        id="advisor-agency-code"
        label="Agency Code"
        value={agencyCode}
        onChange={(e) => setAgencyCode(e.target.value)}
        placeholder="Leave blank for Non QR"
      />
      <SelectField
        id="advisor-status"
        label="Status"
        value={status}
        onChange={(e) => setStatus(e.target.value as "active" | "inactive")}
        options={[
          { value: "active", label: "Active" },
          { value: "inactive", label: "Inactive" },
        ]}
      />
    </Modal>
  );
}
