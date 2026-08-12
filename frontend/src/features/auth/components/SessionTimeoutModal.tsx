// "Session Expiring" warning shown at 9 minutes idle, 60 seconds before auto-logout
// (see useIdleTimeout.ts). A plain overlay, not a routed page — it must be able to
// interrupt whatever screen the user is on, anywhere in the authenticated app.
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-sm rounded-card bg-card border border-border shadow-card p-6 text-center">
        <h2 className="text-lg font-semibold text-text mb-2">Session Expiring</h2>
        <p className="text-sm text-text/60 mb-6">
          Your session will expire in <span className="font-semibold text-text">{secondsRemaining}</span> second
          {secondsRemaining === 1 ? "" : "s"}.
        </p>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onContinue}
            className="w-full rounded-lg bg-primary text-white text-sm font-medium py-2.5"
          >
            Continue Session
          </button>
          <button
            type="button"
            onClick={onLogout}
            className="w-full rounded-lg border border-border text-sm font-medium py-2.5 text-text/70 hover:bg-background"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  );
}
