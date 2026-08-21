import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { TextareaField } from "@/components/forms/TextareaField";
import { rejectLead } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";

// My Leads -> Rejected (spec section 17) — reason is required and recorded (rejected_by/
// rejected_at, audited via a `rejected` LeadActivity, decision 125). Only reachable for
// an already-assigned lead; the backend enforces this regardless of what this modal does.
export function RejectLeadModal({
  leadId,
  leadCode,
  onClose,
  onRejected,
}: {
  leadId: string;
  leadCode: string;
  onClose: () => void;
  onRejected: () => void;
}) {
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!reason.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await rejectLead(leadId, reason.trim());
      onRejected();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Reject Lead"
      description={`Lead ${leadCode}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" loading={isSubmitting} disabled={!reason.trim()} onClick={onSubmit}>
            Reject
          </Button>
        </>
      }
    >
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      <TextareaField
        label="Reason"
        required
        rows={3}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="e.g. Customer not interested"
      />
    </Modal>
  );
}
