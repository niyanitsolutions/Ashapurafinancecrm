import type { ReactNode } from "react";
import { Link, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";

// Its own shell, not Dashboard's AppShell/Sidebar or CustomerPortalLayout — a Referral
// Partner is a distinct external actor with its own, simpler chrome, mirroring exactly
// how Module 6B gave Customer its own portal shell rather than reusing Dashboard's.
export function ReferralPartnerPortalLayout({ children }: { children?: ReactNode }) {
  const { logout } = useAuth();

  const onLogout = () => {
    logout();
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border h-16 flex items-center justify-between px-6">
        <Link to="/referral-portal" className="text-lg font-semibold text-primary">
          AFS Referral Partner Portal
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link to="/referral-portal" className="text-text/70 hover:text-primary">
            Dashboard
          </Link>
          <Link to="/referral-portal/leads" className="text-text/70 hover:text-primary">
            My Leads
          </Link>
          <Link to="/referral-portal/commissions" className="text-text/70 hover:text-primary">
            Commission History
          </Link>
          <button type="button" onClick={onLogout} className="text-danger hover:underline">
            Logout
          </button>
        </nav>
      </header>
      <main className="p-6">{children ?? <Outlet />}</main>
    </div>
  );
}
