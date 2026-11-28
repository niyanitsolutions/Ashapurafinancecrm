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
      <header className="border-b border-border bg-card px-4 py-4 sm:px-6">
        <Link to="/referral-portal" className="text-lg font-semibold text-primary">AFS Partner Portal</Link>
        <nav aria-label="Partner navigation" className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm">
          {[["Dashboard","/referral-portal"],["Complete KYC","/referral-portal/kyc"],["My Referrals","/referral-portal/leads"],["Add Customer","/referral-portal/add-customer"],["Generate Customer Link","/referral-portal/links"],["Commission Rules","/referral-portal/rules"],["My Commissions","/referral-portal/commissions"],["Payout History","/referral-portal/payouts"],["Profile & Security","/referral-portal/security"],["Notifications","/referral-portal/notifications"]].map(([label,to])=><Link className="text-text/70 hover:text-primary" to={to} key={to}>{label}</Link>)}
          <button type="button" onClick={onLogout} className="text-danger hover:underline">Log out</button>
        </nav>
      </header>
      <main className="p-6">{children ?? <Outlet />}</main>
    </div>
  );
}
