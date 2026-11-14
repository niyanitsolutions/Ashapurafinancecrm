import { useState, type ReactNode } from "react";
import { Button, type ButtonVariant } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";

// Shared confirmation dialog for destructive/impactful actions (Reset Password, Deactivate,
// Delete, ...) that previously fired immediately on click with no confirmation step.
export function ConfirmDialog({
  open,
  title,
  message = "This action cannot be undone.",
  confirmLabel = "Confirm",
  confirmVariant = "primary",
  onConfirm,
  onClose,
  children,
  confirmDisabled = false,
}: {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  confirmVariant?: ButtonVariant;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
  children?: ReactNode;
  confirmDisabled?: boolean;
}) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!open) return null;

  const handleConfirm = async () => {
    setIsSubmitting(true);
    try {
      await onConfirm();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={confirmDisabled} variant={confirmVariant} size="sm" loading={isSubmitting} onClick={handleConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-textSecondary">{message}</p>
      {children}
    </Modal>
  );
}
