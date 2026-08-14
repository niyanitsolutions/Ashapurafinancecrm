import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";

// "Session Expiring" warning shown at 9 minutes idle, 60 seconds before auto-logout
// (see useIdleTimeout.ts). Must be able to interrupt whatever screen the user is on,
// anywhere in the authenticated app. Backdrop click / Escape map to onContinue (not a
// no-op, not onLogout) — the safe default is to keep the session alive, matching what the
// primary button already does.
export function SessionTimeoutModal({
  secondsRemaining,
  onContinue,
  onLogout,
}: {
  secondsRemaining: number;
  onContinue: () => void;
  onLogout: () => void;
}) {
  return (
    <Modal
      open
      onClose={onContinue}
      title="Session Expiring"
      size="sm"
      footer={
        <div className="flex w-full flex-col gap-2">
          <Button onClick={onContinue}>Continue Session</Button>
          <Button variant="secondary" onClick={onLogout}>
            Logout
          </Button>
        </div>
      }
    >
      <p className="text-sm text-text/60">
        Your session will expire in <span className="font-semibold text-text">{secondsRemaining}</span> second
        {secondsRemaining === 1 ? "" : "s"}.
      </p>
    </Modal>
  );
}
