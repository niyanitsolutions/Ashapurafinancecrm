import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import {
  addLoanFollowUp,
  getLoanCaseTimeline,
  holdLoanCase,
  updateLoanCaseStatus,
  type CaseTimelineEntry,
  type LoanCaseDetail,
} from "@/features/loan_management/api";
import { FollowUpHistory } from "@/features/loan_management/components/FollowUpHistory";
import {
  ReEligibilitySchedulingModal,
  type ReEligibilityRejectPayload,
} from "@/features/loan_management/components/ReEligibilitySchedulingModal";
import { LOAN_STATUS_LABELS } from "@/features/loan_management/constants";
import { HOLD_REASONS } from "@/features/workflow_engine/holdReasons";

// Re-Eligible Case Management enhancement — the dedicated Update modal for a Re-Eligible
// loan case:
//   - "Move Case To" dropdown, populated from the case's own `allowed_next_statuses`
//     (the backend transition graph is the single source of truth — never a hard-coded
//     list). Rejected routes through the existing Re-Eligibility scheduling popup; On
//     Hold through the existing hold-reason flow.
//   - Next Follow-up date + Add Comment (a new note every time, never overwriting).
//   - Follow-up & Comment History grouped Past → Today → Future.
// The follow-up date is a reminder only — it NEVER moves the case.

export function ReEligibleUpdateModal({
  loanCase,
  canEdit,
  onClose,
  onUpdated,
}: {
  loanCase: LoanCaseDetail;
  canEdit: boolean;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const caseId = loanCase.id;
  const [nextStatus, setNextStatus] = useState("");
  const [holdReason, setHoldReason] = useState(HOLD_REASONS[0].value);
  const [followUpDate, setFollowUpDate] = useState("");
  const [comment, setComment] = useState("");
  const [notes, setNotes] = useState<CaseTimelineEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showRejectSchedule, setShowRejectSchedule] = useState(false);

  const destinations = loanCase.allowed_next_statuses.filter((s) => s in LOAN_STATUS_LABELS);

  const loadNotes = () => {
    getLoanCaseTimeline(caseId)
      .then(setNotes)
      .catch(() => setNotes([]));
  };
  useEffect(loadNotes, [caseId]);

  const runStatus = async (fn: () => Promise<LoanCaseDetail>) => {
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      const updated = await fn();
      onUpdated();
      if (updated.current_status !== "re_eligible") onClose();
      else setMessage("Updated.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const onUpdateStatus = () => {
    if (!nextStatus) return;
    if (nextStatus === "rejected") {
      setShowRejectSchedule(true);
      return;
    }
    if (nextStatus === "on_hold") {
      void runStatus(() => holdLoanCase(caseId, holdReason));
      return;
    }
    void runStatus(() => updateLoanCaseStatus(caseId, nextStatus));
  };

  const onAddComment = async () => {
    if (!comment.trim()) return;
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      await addLoanFollowUp(caseId, { comment: comment.trim(), follow_up_date: followUpDate || undefined });
      setComment("");
      setMessage("Comment added.");
      loadNotes();
      onUpdated(); // parent re-fetches the case (Next Follow-up etc.)
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (showRejectSchedule) {
    return (
      <ReEligibilitySchedulingModal
        caseCode={loanCase.case_code}
        submitting={busy}
        error={error}
        onCancel={() => setShowRejectSchedule(false)}
        onConfirm={(payload: ReEligibilityRejectPayload) => {
          setShowRejectSchedule(false);
          void runStatus(() =>
            updateLoanCaseStatus(caseId, "rejected", payload.remarks, {
              re_eligibility: payload.re_eligibility,
              re_eligible_date: payload.re_eligible_date,
            }),
          );
        }}
      />
    );
  }

  return (
    <Modal open onClose={onClose} title={`Update ${loanCase.case_code}`} description="Current Status: Re-Eligible" size="lg">
      <div className="space-y-6">
        {message && <p className="text-sm text-success">{message}</p>}
        {error && <p className="text-sm text-danger">{error}</p>}

        {canEdit && (
          <div className="space-y-3">
            <SelectField
              label="Move Case To"
              name="next_status"
              value={nextStatus}
              onChange={(e) => setNextStatus(e.target.value)}
              placeholder="Select Status"
              options={destinations.map((s) => ({ value: s, label: LOAN_STATUS_LABELS[s] }))}
            />
            {nextStatus === "on_hold" && (
              <SelectField
                label="Hold Reason"
                name="hold_reason"
                value={holdReason}
                onChange={(e) => setHoldReason(e.target.value)}
                options={HOLD_REASONS.map((r) => ({ value: r.value, label: r.label }))}
              />
            )}
            <Button size="sm" loading={busy} disabled={!nextStatus} onClick={onUpdateStatus}>
              Update Status
            </Button>
          </div>
        )}

        {canEdit && (
          <div className="space-y-2 border-t border-border pt-4">
            <div>
              <label htmlFor="re_eligible_follow_up" className="mb-1.5 block text-sm font-medium text-text">
                Next Follow-up
              </label>
              <input
                id="re_eligible_follow_up"
                type="date"
                value={followUpDate}
                onChange={(e) => setFollowUpDate(e.target.value)}
                className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              <p className="mt-1 text-xs text-textSecondary">
                A reminder only — the case is never moved automatically when this date arrives.
              </p>
            </div>
            <TextareaField
              label="Add Comment"
              name="comment"
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. Customer confirmed they want to continue. Follow up on the date above."
            />
            <Button size="sm" variant="secondary" loading={busy} disabled={!comment.trim()} onClick={onAddComment}>
              Add Comment
            </Button>
          </div>
        )}

        <div className="border-t border-border pt-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-textSecondary">Follow-up &amp; Comment History</h3>
          <FollowUpHistory entries={notes} />
        </div>
      </div>
    </Modal>
  );
}
