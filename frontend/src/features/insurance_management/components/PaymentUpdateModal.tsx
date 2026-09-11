import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { Modal } from "@/components/overlays/Modal";
import type { InsuranceCaseDetail } from "@/features/insurance_management/api";
import { INSURANCE_PAYMENT_STATUS_LABELS } from "@/features/insurance_management/statusControl";

export interface PaymentUpdatePayload {
  amount_paid: number;
}

function formatINR(value: number): string {
  return `₹${value.toLocaleString("en-IN")}`;
}

// "Update Payment" — records Amount Paid against the case's (already-recorded) Premium.
// Payment Status / Balance shown here are a LIVE PREVIEW only, computed the same way the
// backend computes them (`InsurancePaymentStatus.compute`) — never sent in the payload;
// the backend always re-derives the real, persisted status from the saved amount.
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
  const [amountPaid, setAmountPaid] = useState(d.amount_paid != null ? String(d.amount_paid) : "0");

  const parsed = Number(amountPaid);
  const valid = amountPaid.trim() !== "" && !Number.isNaN(parsed) && parsed >= 0 && parsed <= premium;
  const balance = valid ? premium - parsed : null;
  const previewStatus = !valid ? null : parsed <= 0 ? "not_paid" : parsed >= premium ? "fully_paid" : "partially_paid";

  const submit = () => {
    if (!valid) return;
    onConfirm({ amount_paid: parsed });
  };

  return (
    <Modal open onClose={onCancel} title="Update Payment" description={`Case ${detail.case_code} — Premium ${formatINR(premium)}`}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="space-y-3"
      >
        {error && <p className="text-sm text-danger">{error}</p>}

        <FormField
          label="Amount Paid"
          name="amount_paid"
          type="number"
          min="0"
          step="0.01"
          value={amountPaid}
          onChange={(e) => setAmountPaid(e.target.value)}
        />
        {amountPaid.trim() !== "" && !valid && (
          <p className="-mt-2 text-xs text-danger">Amount paid must be between ₹0 and the Premium Amount of {formatINR(premium)}.</p>
        )}

        <div className="rounded border border-border bg-background/50 px-3 py-2 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-text/50">Balance</span>
            <span>{balance != null ? formatINR(balance) : "—"}</span>
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
