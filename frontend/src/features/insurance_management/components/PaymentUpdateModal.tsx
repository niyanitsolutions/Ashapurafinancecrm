import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { Modal } from "@/components/overlays/Modal";
import type { InsuranceCaseDetail } from "@/features/insurance_management/api";
import { INSURANCE_PAYMENT_STATUS_LABELS } from "@/features/insurance_management/statusControl";

export interface PaymentUpdatePayload {
  amount: number;
}

function formatINR(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

// "Add Payment" — the entered amount is ADDED to whatever is already recorded, never a
// replacement of the total (production bug this fixes: a second payment used to
// overwrite the first). Current Paid / Current Balance are shown read-only so staff can
// never mistake this for "enter the new total"; the live preview below the field shows
// what the total/balance/status will become AFTER this payment — computed the same way
// the backend computes them, never sent in the payload. The backend always re-derives
// the real, persisted cumulative total/status atomically from the saved amount.
export function PaymentUpdateModal({
  detail,
  submitting = false,
  error,
  onCancel,
  onConfirm,
}: {
  detail: InsuranceCaseDetail;
  submitting?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: PaymentUpdatePayload) => void;
}) {
  const d = detail.insurance_details;
  const premium = d.premium_amount ?? 0;
  const currentPaid = d.amount_paid ?? 0;
  const currentBalance = premium - currentPaid;
  const [amount, setAmount] = useState("");

  const parsed = Number(amount);
  const valid = amount.trim() !== "" && !Number.isNaN(parsed) && parsed > 0 && parsed <= currentBalance;
  const newTotal = valid ? currentPaid + parsed : null;
  const newBalance = valid ? premium - (newTotal ?? 0) : null;
  const previewStatus = newTotal == null ? null : newTotal >= premium ? "fully_paid" : "partially_paid";

  const submit = () => {
    if (!valid) return;
    onConfirm({ amount: parsed });
  };

  return (
    <Modal open onClose={onCancel} title="Add Payment" description={`Case ${detail.case_code} — Premium ${formatINR(premium)}`}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="space-y-3"
      >
        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="rounded border border-border bg-background/50 px-3 py-2 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-text/50">Current Paid</span>
            <span>{formatINR(currentPaid)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text/50">Current Balance</span>
            <span>{formatINR(currentBalance)}</span>
          </div>
        </div>

        <FormField
          label="Add Payment Amount"
          name="amount"
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Amount being collected now"
        />
        {amount.trim() !== "" && !valid && (
          <p className="-mt-2 text-xs text-danger">
            Enter an amount greater than ₹0 and no more than the remaining balance of {formatINR(currentBalance)}.
          </p>
        )}

        <div className="rounded border border-border bg-background/50 px-3 py-2 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-text/50">Total Paid (after this payment)</span>
            <span>{newTotal != null ? formatINR(newTotal) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text/50">Remaining Balance</span>
            <span>{newBalance != null ? formatINR(newBalance) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text/50">Payment Status</span>
            <span>{previewStatus ? INSURANCE_PAYMENT_STATUS_LABELS[previewStatus] : "—"}</span>
          </div>
        </div>

        <div className="flex gap-2 pt-1">
          <Button type="submit" className="flex-1" loading={submitting} disabled={submitting || !valid}>
            Save
          </Button>
          <Button type="button" variant="secondary" className="flex-1" disabled={submitting} onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}
