import { useState, type ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { CustomerNotificationBell } from "@/features/customer/components/CustomerNotificationBell";
import { DocumentRejectionAlert } from "@/features/customer/components/DocumentRejectionAlert";
import { Icon, type IconName } from "@/theme/icons";
import "../portal.css";

const NAV_ITEMS: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/portal", label: "Overview", icon: "grid", end: true },
  { to: "/portal/applications", label: "My applications", icon: "applications" },
  { to: "/portal/documents", label: "Document centre", icon: "documents" },
  { to: "/portal/messages", label: "Messages", icon: "chat" },
  { to: "/portal/alerts", label: "Notifications", icon: "bell" },
  { to: "/portal/profile", label: "My profile", icon: "user" },
  { to: "/portal/support", label: "Help & support", icon: "shield-check" },
];

export function CustomerPortalLayout({ children }: { children?: ReactNode }) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const links = NAV_ITEMS.map(item => <NavLink key={item.to} to={item.to} end={item.end}
    className="portal-nav-link" onClick={() => setOpen(false)}>
    <Icon name={item.icon} className="h-5 w-5 shrink-0" />{item.label}
  </NavLink>);
  return <div className="customer-portal">
    <a href="#portal-main" className="sr-only focus:not-sr-only">Skip to main content</a>
    <header className="portal-shell-header">
      <Link to="/portal" className="portal-brand"><span className="portal-brand-mark">AFS</span>
        <span>Ashapura Financial Services<small>Your customer portal</small></span></Link>
      <div className="portal-header-actions"><CustomerNotificationBell />
        <button type="button" className="portal-menu-toggle" aria-label="Customer navigation" aria-expanded={open}
          aria-controls="portal-mobile-navigation" onClick={() => setOpen(value => !value)}><Icon name="grid" className="h-5 w-5" /></button>
      </div>
    </header>
    <nav id="portal-mobile-navigation" className="portal-mobile-nav" data-open={open} aria-label="Customer mobile navigation">{links}
      <button type="button" className="portal-nav-link" onClick={() => void logout()}>Sign out</button>
    </nav>
    <div className="portal-shell-grid">
      <aside className="portal-sidebar"><nav aria-label="Customer navigation">{links}</nav>
        <div className="portal-sidebar-help"><p>We're here to help with your application.</p><Link to="/portal/support">Contact support</Link>
          <button type="button" className="block" onClick={() => void logout()}>Sign out</button></div>
      </aside>
      <main className="portal-shell-main" id="portal-main" tabIndex={-1}>{children ?? <Outlet />}</main>
    </div>
    <DocumentRejectionAlert />
  </div>;
}
