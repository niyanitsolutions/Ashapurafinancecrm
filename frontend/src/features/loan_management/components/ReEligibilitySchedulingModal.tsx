import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import type { ReEligibilityChoice } from "@/features/loan_management/api";
import { todayISTDateString } from "@/shared/dateFormat";

// Reject → Re-Eligibility scheduling (production add-on). Presentational only: it
// collects the schedule + remarks and hands them back via `onConfirm`; the caller
// (UpdateLoanCaseModal) performs the actual reject call — the generic status control's
// `updateLoanCaseStatus(..., "rejected", ...)` or Final Evaluation's
// `recordFinalEvaluation({ decision: "rejected", ... })` — so the same popup backs every
// stage that can Reject. Mirrors TopUpSchedulingModal's option layout.
//
// "No" is an explicit business decision meaning "never automatically Re-Eligible" — NOT
// a default duration. Remarks are mandatory, same rule the backend already enforces for
// a rejection reason.

const OPTIONS: { value: ReEligibilityChoice; label: string }[] = [
  { value: "3_months", label: "3 Months" },
  { value: "6_months", label: "6 Months" },
  { value: "9_months", label: "9 Months" },
  { value: "12_months", label: "12 Months" },
  { value: "custom", label: "Custom" },
  { value: "no", label: "No" },
];

export interface ReEligibilityRejectPayload {
  re_eligibility: ReEligibilityChoice;
  re_eligible_date?: string;
  remarks: string;
}

export function ReEligibilitySchedulingModal({
  caseCode,
  submitting = false,
  error,
  onCancel,
  onConfirm,
}: {
  caseCode?: string;
  submitting?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: ReEligibilityRejectPayload) => void;
}) {
  const [choice, setChoice] = useState<ReEligibilityChoice | "">("");
  const [customDate, setCustomDate] = useState("");
  const [remarks, setRemarks] = useState("");

  const today = todayISTDateString();
  const customDateInvalid = choice === "custom" && Boolean(customDate) && customDate <= today;
  const canSubmit =
    Boolean(choice) &&
    remarks.trim().length > 0 &&
    (choice !== "custom" || (Boolean(customDate) && !customDateInvalid)) &&
    !submitting;

  return (
    <Modal open onClose={onCancel} title="Reject Loan Case" description={caseCode ? `Case ${caseCode}` : undefined}>
      <div className="space-y-4">
        {error && <p className="text-sm text-danger">{error}</p>}

        <div>
          <h3 className="mb-2 text-sm font-semibold text-text/70">
            How many months after rejection should this case become Re-Eligible?
          </h3>
          <div className="space-y-2">
            {OPTIONS.map((opt) => (
              <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm text-text">
                <input
                  type="radio"
                  name="re-eligibility"
                  value={opt.value}
                  checked={choice === opt.value}
                  onChange={() => setChoice(opt.value)}
                  className="accent-primary"
                />
                {opt.label}
              </label>
            ))}
          </div>
          {choice === "no" && (
            <p className="mt-2 text-xs text-textSecondary">
              This case will never automatically become Re-Eligible.
            </p>
          )}
        </div>

        {choice === "custom" && (
          <div>
            <FormField
              label="Re-Eligible Date"
              name="re_eligible_date"
              type="date"
              value={customDate}
              min={today}
              onChange={(e) => setCustomDate(e.target.value)}
              required
            />
            {customDateInvalid && <p className="mt-1 text-xs text-danger">The Re-Eligible date must be in the future.</p>}
          </div>
        )}

        <TextareaField
          label="Remarks (mandatory)"
          name="reject_remarks"
          value={remarks}
          onChange={(e) => setRemarks(e.target.value)}
          rows={3}
          required
        />

        <div className="flex gap-2">
          <Button
            variant="danger"
            className="flex-1"
            loading={submitting}
            disabled={!canSubmit}
            onClick={() =>
              onConfirm({
                re_eligibility: choice as ReEligibilityChoice,
                re_eligible_date: choice === "custom" ? customDate : undefined,
                remarks: remarks.trim(),
              })
            }
          >
            Confirm Reject
          </Button>
          <Button variant="secondary" className="flex-1" disabled={submitting} onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
    </Modal>
  );
}
