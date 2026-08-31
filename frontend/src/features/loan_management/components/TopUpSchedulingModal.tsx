import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import { getLoanCase, scheduleTopUp, type LoanCaseDetail } from "@/features/loan_management/api";
import { formatISTDate } from "@/shared/dateFormat";

// Top Up Loan (production add-on) — the ONE scheduling popup reused by every entry
// point per spec: the Disbursed list's "Top Up" action (initial scheduling), the
// automatic popup right after a successful disburse, and the Top Up Loan list's
// "Rejected" action (reject + reschedule). Self-fetches the case (mirrors
// MoveApplicationToLoanManagementModal's pattern) so every caller only needs to pass a
// `caseId` — no prop threading of customer/disbursed-date details.

const PERIOD_OPTIONS: { value: string; label: string }[] = [
  { value: "3_months", label: "3 Months" },
  { value: "6_months", label: "6 Months" },
  { value: "12_months", label: "12 Months" },
  { value: "no", label: "No" },
  { value: "custom", label: "Custom" },
];

const PERIOD_MONTHS: Record<string, number> = { "3_months": 3, "6_months": 6, "12_months": 12 };

// Mirrors the backend's `add_calendar_months` exactly (calendar months, day clamped to
// the target month's real length) — display preview only, so a customer/staff member
// isn't left guessing what date they're about to schedule; the backend independently
// computes and persists the authoritative value from the case's own stored
// `disbursed_at`, never trusting this client-side echo.
function addCalendarMonthsToIsoDate(isoDate: string, months: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const monthIndex = month - 1 + months;
  const targetYear = year + Math.floor(monthIndex / 12);
  const targetMonth = ((monthIndex % 12) + 12) % 12;
  const lastDay = new Date(targetYear, targetMonth + 1, 0).getDate();
  const targetDay = Math.min(day, lastDay);
  return `${targetYear}-${String(targetMonth + 1).padStart(2, "0")}-${String(targetDay).padStart(2, "0")}`;
}

function displayIsoDate(isoDate: string): string {
  // Noon UTC keeps the formatted IST calendar date stable regardless of DST/offset
  // edge cases — see formatISTDate, which converts to Asia/Kolkata before formatting.
  return formatISTDate(`${isoDate}T12:00:00.000Z`);
}

export function TopUpSchedulingModal({
  caseId,
  onClose,
  onScheduled,
}: {
  caseId: string;
  onClose: () => void;
  onScheduled: () => void;
}) {
  const [loanCase, setLoanCase] = useState<LoanCaseDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [period, setPeriod] = useState("");
  const [customDate, setCustomDate] = useState("");
  const [remarks, setRemarks] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLoanCase(caseId)
      .then(setLoanCase)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [caseId]);

  const disbursedAtIsoDate = loanCase?.loan_details.disbursed_at ? loanCase.loan_details.disbursed_at.slice(0, 10) : null;

  const eligibilityPreview: string | null =
    disbursedAtIsoDate && period in PERIOD_MONTHS
      ? addCalendarMonthsToIsoDate(disbursedAtIsoDate, PERIOD_MONTHS[period])
      : period === "custom" && customDate
        ? customDate
        : null;

  const customDateInvalid = period === "custom" && Boolean(customDate) && Boolean(disbursedAtIsoDate) && customDate < (disbursedAtIsoDate as string);

  const canSubmit = Boolean(period) && (period !== "custom" || (Boolean(customDate) && !customDateInvalid));

  const onSubmit = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      await scheduleTopUp(caseId, {
        period, custom_date: period === "custom" ? customDate : undefined, remarks: remarks.trim() || undefined,
      });
      onScheduled();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Top Up Loan" description={loanCase ? `Case ${loanCase.case_code}` : undefined}>
      {isLoading ? (
        <p className="py-6 text-center text-sm text-textSecondary">Loading…</p>
      ) : (
        <div className="space-y-4">
          {error && <p className="text-sm text-danger">{error}</p>}

          {loanCase && (
            <div className="space-y-0.5 rounded-lg bg-background p-3 text-sm text-text">
              <p>
                Customer: <span className="font-medium">{loanCase.customer?.full_name ?? loanCase.customer_name ?? "—"}</span>
              </p>
              <p>
                Case: <span className="font-medium">{loanCase.case_code}</span>
              </p>
              <p>
                Disbursed Date:{" "}
                <span className="font-medium">{disbursedAtIsoDate ? displayIsoDate(disbursedAtIsoDate) : "—"}</span>
              </p>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-sm font-semibold text-text/70">Top Up Eligibility</h3>
            <div className="space-y-2">
              {PERIOD_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm text-text">
                  <input
                    type="radio"
                    name="top-up-period"
                    value={opt.value}
                    checked={period === opt.value}
                    onChange={() => setPeriod(opt.value)}
                    className="accent-primary"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          {period === "custom" && (
            <div>
              <FormField
                label="Custom Eligibility Date"
                name="custom_eligibility_date"
                type="date"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
                required
              />
              {customDateInvalid && (
                <p className="mt-1 text-xs text-danger">The custom eligibility date cannot be earlier than the disbursed date.</p>
              )}
            </div>
          )}

          {eligibilityPreview && !customDateInvalid && (
            <p className="text-sm text-text">
              Eligibility Date: <span className="font-semibold">{displayIsoDate(eligibilityPreview)}</span>
            </p>
          )}

          <TextareaField label="Remarks" name="top_up_remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} rows={3} />

          <Button className="w-full" loading={isSubmitting} disabled={!canSubmit} onClick={onSubmit}>
            Submit
          </Button>
        </div>
      )}
    </Modal>
  );
}
