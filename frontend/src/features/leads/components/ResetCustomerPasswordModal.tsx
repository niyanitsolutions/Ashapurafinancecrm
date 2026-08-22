import { useState } from "react";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { resetCustomerPassword } from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";

// Staff "Reset Customer Password" action (My Leads -> Update Lead -> Create Customer
// Account panel, once an account already exists) — reuses the existing customer
// authentication system end to end (see backend CustomerService.reset_customer_password);
// this modal only collects and confirms the new value client-side.
export function ResetCustomerPasswordModal({
  leadId,
  onClose,
  onReset,
}: {
  leadId: string;
  onClose: () => void;
  onReset: () => void;
}) {
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;
  const canSubmit = newPassword.length >= 8 && newPassword === confirmPassword;

  const onSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await resetCustomerPassword(leadId, newPassword, confirmPassword);
      onReset();
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
      size="sm"
      title="Reset Customer Password"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" loading={isSubmitting} disabled={!canSubmit} onClick={onSubmit}>
            Reset Password
          </Button>
        </>
      }
    >
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      <div className="space-y-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text">New Password</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text">Confirm Password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          {mismatch && <p className="mt-1 text-xs text-danger">Passwords do not match.</p>}
        </div>
        <p className="text-xs text-textSecondary">
          The customer's existing sessions will be signed out and the new password takes effect immediately.
        </p>
      </div>
    </Modal>
  );
}
