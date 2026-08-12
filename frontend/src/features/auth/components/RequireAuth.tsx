import { Navigate, Outlet, useLocation } from "react-router-dom";
import { SessionGuard } from "@/features/auth/components/SessionGuard";
import { useAuth } from "@/features/auth/useAuth";

const FORCE_CHANGE_PASSWORD_PATH = "/force-change-password";

// Route guard added in Module 2 — Module 1 had no protected routes to guard yet.
export function RequireAuth() {
  const { accessToken, isBootstrapping, mustChangePassword } = useAuth();
  const location = useLocation();

  if (isBootstrapping) {
    return null; // avoid a login-page flash while the silent refresh-on-load resolves
  }
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  // Employees created with an Owner-set temporary password must change it before
  // reaching anything else — re-checked on every navigation, so it can't be routed
  // around (see employee/service.py::create_employee, Rule 3/9).
  if (mustChangePassword && location.pathname !== FORCE_CHANGE_PASSWORD_PATH) {
    return <Navigate to={FORCE_CHANGE_PASSWORD_PATH} replace />;
  }
  // Idle-timeout/auto-logout applies to every authenticated role — this is the one
  // route guard all of Owner/Employee/Referral Partner/Customer already pass through.
  return (
    <SessionGuard>
      <Outlet />
    </SessionGuard>
  );
}

// Owner-only routes (e.g. Employee List/Create) — Employee gets redirected to their own
// profile rather than a bare error page, matching what a click into a disallowed nav
// item should feel like even though there's no sidebar yet to hide it from them.
export function RequireOwner() {
  const { role, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return null;
  }
  if (role !== "owner") {
    return <Navigate to="/profile" replace />;
  }
  return <Outlet />;
}
