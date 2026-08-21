import { Link, useLocation } from "react-router-dom";
import { useNavKeys } from "@/components/layout/useNavKeys";
import { hasNavAccess } from "@/components/layout/navAccess";

export interface ModuleTab {
  label: string;
  to: string;
  /** Nav key(s) gating this tab's visibility — same allow-list the sidebar uses.
   * Omit for tabs with no dedicated permission key of their own (e.g. a stub tab
   * nested under an already-gated module). */
  matchKey?: string | string[];
  /** Match this tab as active only on an exact pathname match, not by prefix —
   * needed when this tab's own `to` is itself a prefix of a sibling tab's `to`
   * (e.g. a "directory" tab at the module's bare base path, like Master Settings
   * at /settings sitting alongside /settings/lead-sources). */
  exact?: boolean;
  /** Live count badge next to the label (e.g. Leads' Fresh/My Leads/Document
   * Collection/Rejected/Assigned tabs — decision 125). Omit for a tab with no count
   * concept — every other module's tabs simply don't set this. */
  count?: number;
}

// Shared in-page tab strip for modules whose sidebar entry was consolidated
// from several leaves into one (see navConfig.ts). Reuses the same active-tab
// visual language already hand-rolled in CommunicationPage/EmployeeDetailsPage
// (border-b-2, primary accent) and the same nav-key visibility check Sidebar
// uses, so a tab never exposes a page the user isn't permitted to see.
export function ModuleTabs({ tabs }: { tabs: ModuleTab[] }) {
  const location = useLocation();
  const availableKeys = useNavKeys();

  const visibleTabs = tabs.filter((tab) => hasNavAccess(availableKeys, tab.matchKey));
  if (visibleTabs.length === 0) return null;

  const isActive = (tab: ModuleTab) =>
    tab.exact ? location.pathname === tab.to : location.pathname === tab.to || location.pathname.startsWith(`${tab.to}/`);

  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border bg-card px-4 lg:px-6">
      {visibleTabs.map((tab) => {
        const active = isActive(tab);
        return (
          <Link
            key={tab.to}
            to={tab.to}
            className={`shrink-0 whitespace-nowrap px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
              active ? "border-primary text-primary" : "border-transparent text-text/60 hover:text-text"
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span
                className={`ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full px-1.5 py-0.5 text-2xs font-semibold ${
                  active ? "bg-primary/10 text-primary" : "bg-text/10 text-textSecondary"
                }`}
              >
                {tab.count}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
