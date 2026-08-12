import { useMemo } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useNavKeys } from "@/components/layout/useNavKeys";
import { Icon } from "@/theme/icons";
import { NAV_SECTIONS, type NavLeaf } from "@/components/layout/navConfig";
import { hasNavAccess } from "@/components/layout/navAccess";
import { useAuth } from "@/features/auth/useAuth";
import { useProfile } from "@/features/auth/useProfile";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  employee: "Employee",
  referral_partner: "Referral Partner",
  customer: "Customer",
};

// Bottom-of-sidebar identity card (Power BI/Salesforce-style) — reuses the same cached
// `useProfile()` query Topbar's ProfileMenu already reads, so mounting both here and there
// costs one network request total, not two (React Query dedupes on the shared queryKey).
function SidebarProfileCard({ isCollapsed, onToggleCollapsed }: { isCollapsed: boolean; onToggleCollapsed: () => void }) {
  const { role } = useAuth();
  const { data: profile } = useProfile();
  const mobile = profile?.mobile ?? "";
  const initials = mobile ? mobile.slice(-2) : "?";
  const roleLabel = (role && ROLE_LABELS[role]) || "Account";

  return (
    <div className="border-t border-white/10 p-3 shrink-0">
      <div className={`flex items-center gap-2.5 rounded-xl px-2 py-2 ${isCollapsed ? "justify-center" : ""}`}>
        <div className="h-9 w-9 shrink-0 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-semibold">
          {initials}
        </div>
        {!isCollapsed && (
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-white truncate">{mobile || "Loading…"}</p>
            <p className="text-2xs text-white/45 truncate">{roleLabel}</p>
          </div>
        )}
        {!isCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="shrink-0 text-white/40 hover:text-white transition-colors"
          >
            <Icon name="chevron-left" className="h-4 w-4" />
          </button>
        )}
      </div>
      {isCollapsed && (
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label="Expand sidebar"
          title="Expand sidebar"
          className="mt-2 w-full flex items-center justify-center text-white/40 hover:text-white transition-colors"
        >
          <Icon name="chevron-right" className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

// Nav visibility stays 100% server-driven (`nav_items` catalog, permission-filtered —
// see docs/decisions/DECISIONS.md #033): this component only adds grouping/icons on
// top of whichever keys the API actually returns, via navConfig.ts. A leaf never
// renders unless its matchKey is present in the live response.
export function Sidebar({
  isOpen, onClose, isCollapsed, onToggleCollapsed,
}: {
  isOpen: boolean;
  onClose: () => void;
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const availableKeys = useNavKeys();
  const location = useLocation();
  const { role } = useAuth();

  const visibleSections = useMemo(() => {
    if (!availableKeys) return [];
    return NAV_SECTIONS.map((section) => ({
      ...section,
      items: section.items.filter((item) => hasNavAccess(availableKeys, item.matchKey)),
    })).filter((section) => section.items.length > 0);
  }, [availableKeys]);

  // A couple of consolidated entries bundle an Owner-only destination with a
  // permission-only one (see NavLeaf.employeeTo) — non-owners land on the
  // permission-only one instead of hitting an Owner-only redirect.
  const resolveTo = (item: NavLeaf) => (role !== "owner" && item.employeeTo ? item.employeeTo : item.to);

  const isLeafActive = (item: NavLeaf) => {
    const href = resolveTo(item);
    const qIndex = href.search(/[?#]/);
    const pathname = qIndex === -1 ? href : href.slice(0, qIndex);
    const rest = qIndex === -1 ? "" : href.slice(qIndex);
    if (pathname === "/") return location.pathname === "/";
    if (item.exact) return location.pathname === pathname && location.search + location.hash === rest;
    if (location.pathname === pathname || location.pathname.startsWith(`${pathname}/`)) return true;
    return (item.activePrefixes ?? []).some((prefix) => location.pathname === prefix || location.pathname.startsWith(`${prefix}/`));
  };

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/40 z-20 lg:hidden" onClick={onClose} />}
      <aside
        className={`fixed inset-y-0 left-0 bg-sidebar text-white flex flex-col z-30 transition-[transform,width] duration-200 lg:translate-x-0 shadow-dropdown ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } ${isCollapsed ? "w-[76px]" : "w-[280px]"}`}
      >
        <div className="h-16 flex items-center justify-between px-4 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="h-9 w-9 shrink-0 rounded-xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center font-bold text-sm shadow-card">AFS</div>
            {!isCollapsed && <span className="text-base font-semibold text-white truncate">Financial CRM</span>}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-2.5 space-y-5">
          {visibleSections.map((section, sectionIndex) => (
            <div key={section.label ?? `top-${sectionIndex}`}>
              {section.label && !isCollapsed && (
                <div className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-white/35">{section.label}</div>
              )}
              <div className="space-y-1">
                {section.items.map((item) => {
                  if (item.comingSoon) {
                    return (
                      <div
                        key={item.to}
                        title={isCollapsed ? `${item.label} — coming soon` : undefined}
                        aria-disabled="true"
                        className={`flex items-center gap-3 px-3 py-2.5 rounded-card text-sm text-white/35 cursor-not-allowed select-none ${
                          isCollapsed ? "justify-center px-0" : ""
                        }`}
                      >
                        <Icon name={item.icon} className="h-[18px] w-[18px] shrink-0" />
                        {!isCollapsed && (
                          <span className="flex-1 flex items-center justify-between gap-2 min-w-0">
                            <span className="truncate">{item.label}</span>
                            <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-white/40 bg-white/10 rounded-full px-2 py-0.5">
                              Soon
                            </span>
                          </span>
                        )}
                      </div>
                    );
                  }
                  const active = isLeafActive(item);
                  return (
                    <NavLink
                      key={item.to}
                      to={resolveTo(item)}
                      onClick={onClose}
                      title={isCollapsed ? item.label : undefined}
                      className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-card text-sm transition-all duration-150 ${
                        active
                          ? "bg-primary text-white font-medium shadow-card"
                          : "text-white/70 hover:bg-primary/15 hover:text-white hover:translate-x-0.5"
                      } ${isCollapsed ? "justify-center px-0" : ""}`}
                    >
                      {active && !isCollapsed && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-white/90" />
                      )}
                      <Icon name={item.icon} className="h-[18px] w-[18px] shrink-0" />
                      {!isCollapsed && <span className="truncate">{item.label}</span>}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
          {availableKeys && visibleSections.length === 0 && !isCollapsed && (
            <p className="px-3 text-sm text-gray-500">No modules available yet.</p>
          )}
        </nav>

        <SidebarProfileCard isCollapsed={isCollapsed} onToggleCollapsed={onToggleCollapsed} />
      </aside>
    </>
  );
}
