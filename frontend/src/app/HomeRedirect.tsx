import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";

// The index route ("/") — a pure redirect decision, never renders visible content
// itself. Owner/Employee go to /dashboard (a real route nested inside AppShell,
// alongside every other authenticated page — see router.tsx); a Customer goes to the
// portal instead. Previously this returned <DashboardPage/> directly, which rendered it
// as a SIBLING of AppShell instead of a child, silently skipping the Sidebar/Topbar —
// see docs/decisions/DECISIONS.md for the fix writeup. Anything that needs to resume
// somewhere other than this default routing (a secure link, an idle-timeout auto-logout)
// sends the user through LoginPage's `?return=<path>` instead of through here — see
// LoginPage.tsx.
export function HomeRedirect() {
  const { role } = useAuth();

  if (role === "customer") {
    return <Navigate to="/portal" replace />;
  }

  if (role === "referral_partner") {
    return <Navigate to="/referral-portal" replace />;
  }

  return <Navigate to="/dashboard" replace />;
}
