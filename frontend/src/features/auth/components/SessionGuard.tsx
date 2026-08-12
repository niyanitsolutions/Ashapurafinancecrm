import { useCallback, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { SessionTimeoutModal } from "@/features/auth/components/SessionTimeoutModal";
import { useAuth } from "@/features/auth/useAuth";
import { useIdleTimeout } from "@/features/auth/useIdleTimeout";

// Mounted once, inside RequireAuth (so it's live for every authenticated role — Owner,
// Employee, Referral Partner, Customer — and unmounts/remounts cleanly across
// login/logout) rather than in AppProviders: it needs react-router's navigate/location,
// which aren't available above <RouterProvider>.
export function SessionGuard({ children }: { children: ReactNode }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const onExpire = useCallback(() => {
    // `?return=` is the one mechanism the whole app uses to resume after LoginPage
    // (also used by /apply/:secureCode) — see LoginPage.tsx. Includes `location.search`
    // (not just pathname) so resuming a filtered/paginated list view after an idle
    // timeout lands back on the same slice, not just the same page.
    const returnQuery = `?return=${encodeURIComponent(location.pathname + location.search)}`;
    logout("idle_timeout").finally(() => {
      navigate(`/login${returnQuery}`, { replace: true, state: { message: "Session expired. Please login again." } });
    });
  }, [logout, navigate, location.pathname, location.search]);

  const { isWarning, secondsRemaining, continueSession } = useIdleTimeout(onExpire);

  const onLogoutFromModal = () => {
    logout("manual").finally(() => navigate("/login", { replace: true }));
  };

  return (
    <>
      {children}
      {isWarning && (
        <SessionTimeoutModal secondsRemaining={secondsRemaining} onContinue={continueSession} onLogout={onLogoutFromModal} />
      )}
    </>
  );
}
