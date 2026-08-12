import type { ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { Icon, type IconName } from "@/theme/icons";

const NAV_ITEMS: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/portal", label: "Home", icon: "grid", end: true },
  { to: "/portal/applications", label: "My Applications", icon: "applications" },
  { to: "/portal/documents", label: "Documents", icon: "documents" },
  { to: "/portal/messages", label: "Messages", icon: "chat" },
  { to: "/portal/notifications", label: "Notifications", icon: "bell" },
  { to: "/portal/profile", label: "My Profile", icon: "user" },
  { to: "/portal/support", label: "Support", icon: "shield-check" },
];

// Deliberately its own shell, not Dashboard's AppShell/Sidebar (Owner/Employee-oriented
// nav) — the Customer Portal is a distinct, simpler chrome per the brief's own framing
// of Customer as a separate portal from Owner/Employee. This redesign polishes that
// existing top-bar shape (icons, active-route state, spacing) rather than replacing it.
export function CustomerPortalLayout({ children }: { children?: ReactNode }) {
  const { logout } = useAuth();

  const onLogout = () => {
    logout();
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border flex items-center justify-between px-6 py-3 flex-wrap gap-3">
        <Link to="/portal" className="text-lg font-semibold text-primary shrink-0">
          AFS Financial Services
        </Link>
        <nav className="flex items-center gap-1 text-sm flex-wrap">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-lg px-3 py-2 font-medium transition-colors ${
                  isActive ? "bg-primary/10 text-primary" : "text-text/60 hover:bg-background hover:text-text"
                }`
              }
            >
              <Icon name={item.icon} className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
          <button
            type="button"
            onClick={onLogout}
            className="flex items-center gap-1.5 rounded-lg px-3 py-2 font-medium text-danger hover:bg-danger/10"
          >
            <Icon name="logout" className="h-4 w-4" />
            Logout
          </button>
        </nav>
      </header>
      <main className="p-6">{children ?? <Outlet />}</main>
    </div>
  );
}
