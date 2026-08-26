import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { StatusBadge } from "@/components/badges/Badge";
import { Modal } from "@/components/overlays/Modal";
import {
  getLeadLessApplicationSummary,
  moveLeadLessApplicationToLoanManagement,
  type ApplicationDocumentSummary,
  type LeadListItem,
} from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";

// Production fix "DC vs LM" — the Lead-less counterpart of `UpdateStageModal`'s own
// "Application & Documents" + "Move to Loan Management" section, for a Document
// Collection row with no Lead at all (`lead.is_lead_less`). Deliberately does not reuse
// `UpdateStageModal` itself — that component assumes a real Lead (financial assessment,
// Create Customer Account, `getLead`), none of which apply here. Same underlying gate
// and effect as the Lead-based flow (see backend `LeadService.
// move_lead_less_application_to_loan_management`), just a smaller, Lead-less UI.
export function MoveApplicationToLoanManagementModal({
  lead,
  onClose,
  onChanged,
}: {
  lead: LeadListItem;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [summary, setSummary] = useState<ApplicationDocumentSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lead.application_id) {
      setIsLoading(false);
      return;
    }
    getLeadLessApplicationSummary(lead.application_id)
      .then(setSummary)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [lead.application_id]);

  const onMove = async () => {
    if (!lead.application_id) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await moveLeadLessApplicationToLoanManagement(lead.application_id);
      onChanged();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Move to Loan Management" description={lead.lead_code}>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}

      {isLoading ? (
        <p className="py-6 text-center text-sm text-textSecondary">Loading…</p>
      ) : !lead.application_id ? (
        <p className="text-sm text-textSecondary">No application found.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-textSecondary">Status:</span>
            {summary?.application_status === "submitted" ? (
              <StatusBadge status="submitted" label="Submitted" />
            ) : (
              <StatusBadge status="pending" label="Pending" />
            )}
          </div>
          {summary?.application_status === "submitted" && (
            <p className="text-sm text-text">
              {summary.documents_verified} of {summary.documents_required} required documents verified.
              {/* "I don't have this document" — reported separately from Verified, never
                  folded into it, so this never implies an unavailable document was
                  actually verified. */}
              {summary.documents_not_available > 0 && ` ${summary.documents_not_available} marked not available.`}
            </p>
          )}
          <Link to={`/applications/${lead.application_id}?from=document-collection`} className="inline-block text-sm font-medium text-primary hover:underline">
            View Full Application →
          </Link>

          <div className="border-t border-border pt-4 space-y-2">
            <Button className="w-full" loading={isSubmitting} disabled={!summary?.all_documents_verified} onClick={onMove}>
              Move to Loan Management
            </Button>
            {!summary?.all_documents_verified && (
              <p className="text-xs text-textSecondary">
                {summary?.application_status !== "submitted"
                  ? "The customer must submit their application before it can move to Loan Management."
                  : `${summary?.documents_verified ?? 0} of ${summary?.documents_required ?? 0} required documents verified${
                      summary?.documents_not_available ? ` (${summary.documents_not_available} not available)` : ""
                    } — all must be verified or marked unavailable first.`}
              </p>
            )}
            <Button variant="secondary" className="w-full" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
