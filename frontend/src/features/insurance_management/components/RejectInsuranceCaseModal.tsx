import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import type { InsuranceReEligibilityChoice } from "@/features/insurance_management/api";
import { todayISTDateString } from "@/shared/dateFormat";

// Reject → Re-Eligibility scheduling for an Insurance Case. Presentational: it collects
// the reason + schedule and hands them to `onConfirm`; the caller performs the actual
// `rejectInsuranceCase` call. Insurance offers 3 / 6 / 12 / Custom / No (no 9-month
// option — that is loan-only). "No" means "never automatically Re-Eligible".
const OPTIONS: { value: InsuranceReEligibilityChoice; label: string }[] = [
  { value: "3_months", label: "3 Months" },
  { value: "6_months", label: "6 Months" },
  { value: "12_months", label: "12 Months" },
  { value: "custom", label: "Custom" },
  { value: "no", label: "No" },
];

export interface RejectInsuranceCasePayload {
  reason: string;
  re_eligibility: InsuranceReEligibilityChoice;
  re_eligible_date?: string;
}

export function RejectInsuranceCaseModal({
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
  onConfirm: (payload: RejectInsuranceCasePayload) => void;
}) {
  const [choice, setChoice] = useState<InsuranceReEligibilityChoice | "">("");
  const [customDate, setCustomDate] = useState("");
  const [reason, setReason] = useState("");

  const today = todayISTDateString();
  const customDateInvalid = choice === "custom" && Boolean(customDate) && customDate <= today;
  const canSubmit =
    Boolean(choice) &&
    reason.trim().length > 0 &&
    (choice !== "custom" || (Boolean(customDate) && !customDateInvalid)) &&
    !submitting;

  return (
    <Modal open onClose={onCancel} title="Reject Insurance Case" description={caseCode ? `Case ${caseCode}` : undefined}>
      <div className="space-y-4">
        {error && <p className="text-sm text-danger">{error}</p>}

        <div>
          <h3 className="mb-2 text-sm font-semibold text-text/70">
            When should this case become Re-Eligible to restart?
          </h3>
          <div className="space-y-2">
            {OPTIONS.map((opt) => (
              <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm text-text">
                <input
                  type="radio"
                  name="insurance-re-eligibility"
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
            <p className="mt-2 text-xs text-textSecondary">This case will never automatically become Re-Eligible.</p>
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
          label="Rejection Reason (mandatory)"
          name="insurance_reject_reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
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
                reason: reason.trim(),
                re_eligibility: choice as InsuranceReEligibilityChoice,
                re_eligible_date: choice === "custom" ? customDate : undefined,
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
