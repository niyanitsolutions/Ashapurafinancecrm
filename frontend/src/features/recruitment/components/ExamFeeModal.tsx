import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { Modal } from "@/components/overlays/Modal";
import { recordRecruitmentExamFee, type RecruitmentLeadDetail } from "@/features/recruitment/api";
import { getErrorMessage } from "@/shared/api/errors";

// Marks the exam fee as paid and advances the candidate from Exam Fee Status to Examination.
export function ExamFeeModal({
  lead,
  onClose,
  onSaved,
}: {
  lead: RecruitmentLeadDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [reference, setReference] = useState(lead.exam_fee_reference ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onConfirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await recordRecruitmentExamFee(lead.id, { reference: reference.trim() || undefined });
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
      title="Record Exam Fee"
      description={`${lead.recruitment_code} · ${lead.full_name}`}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button size="sm" onClick={onConfirm} loading={busy}>
            Mark Fee Paid
          </Button>
        </>
      }
    >
      {error && <ErrorBanner message={error} />}
      <p className="mb-3 text-sm text-textSecondary">
        Confirming the exam fee moves the candidate to Examination.
      </p>
      <FormField
        id="exam-fee-reference"
        name="reference"
        label="Payment reference (optional)"
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        placeholder="Receipt / transaction number"
      />
    </Modal>
  );
}
