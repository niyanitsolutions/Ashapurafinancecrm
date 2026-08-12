import { Link } from "react-router-dom";
import { DateScopePill, FiltersButton } from "@/components/layout/HeaderControls";
import { QuickAddMenu } from "@/components/layout/QuickAddMenu";
import { useProfile } from "@/features/auth/useProfile";
import { useAuth } from "@/features/auth/useAuth";
import { NotificationBell } from "@/features/dashboard/components/NotificationBell";
import { ProfileMenu } from "@/features/dashboard/components/ProfileMenu";
import { QuickSearch } from "@/features/dashboard/components/QuickSearch";
import { Icon } from "@/theme/icons";

function greetingForHour(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

const ROLE_LABELS: Record<string, string> = { owner: "Owner", employee: "Team Member" };

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { role } = useAuth();
  // /auth/profile (not /employees/me) — the latter 404s for Owner, who has no Employee
  // row; this needs to work identically for both roles. No display name at this level
  // (see docs/KNOWN_LIMITATIONS.md), so the mobile number is shown instead. Cached via
  // useProfile() — Sidebar's profile card reads the same query, one request total.
  const { data: profile } = useProfile();
  const mobile = profile?.mobile ?? "";

  const greeting = greetingForHour(new Date().getHours());
  const roleLabel = (role && ROLE_LABELS[role]) || null;

  return (
    <header className="bg-card border-b border-border px-4 py-4 lg:px-8 lg:py-5">
      <div className="flex items-center gap-4">
        <button type="button" className="lg:hidden text-text/70 shrink-0" onClick={onMenuClick} aria-label="Open menu">
          <Icon name="menu" className="h-5 w-5" />
        </button>

        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-bold text-text truncate">
            {greeting}
            {roleLabel ? `, ${roleLabel}` : ""} <span aria-hidden="true">👋</span>
          </h1>
          <p className="text-2xs text-textSecondary mt-0.5 hidden sm:block">Here&apos;s what&apos;s happening with your business today.</p>
        </div>

        <div className="hidden xl:flex items-center w-64 shrink-0">
          <QuickSearch />
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <DateScopePill />
          <FiltersButton />
          <QuickAddMenu />
          <Link
            to="/tasks"
            className="hidden sm:flex w-9 h-9 rounded-full hover:bg-background items-center justify-center text-text/70"
            aria-label="Tasks"
            title="Tasks"
          >
            <Icon name="tasks" className="h-5 w-5" />
          </Link>
          <NotificationBell />
          <Link
            to="/settings"
            className="hidden sm:flex w-9 h-9 rounded-full hover:bg-background items-center justify-center text-text/70"
            aria-label="Settings"
            title="Settings"
          >
            <Icon name="settings" className="h-5 w-5" />
          </Link>
          <div className="w-px h-6 bg-border mx-1 hidden sm:block" />
          <ProfileMenu displayName={mobile || "Account"} />
        </div>
      </div>
    </header>
  );
}
