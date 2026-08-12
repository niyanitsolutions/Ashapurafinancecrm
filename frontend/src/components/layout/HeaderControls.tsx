import { useEffect, useRef, useState } from "react";
import { Icon } from "@/theme/icons";

// The reference header has a Date Picker and a Filters button, but no widget provider on
// the backend accepts a date-range or filter parameter — every KPI/chart here is a fixed
// scope (this month, all-time, or last-6-months) computed server-side. Rather than ship a
// picker that looks interactive but silently changes nothing (or invent client-side
// filtering logic that doesn't exist), the Date pill is an honest static label and the
// Filters button opens a small popover naming each section's real scope. Real, useful,
// not pretending to a capability the backend doesn't have.
export function DateScopePill() {
  return (
    <div className="hidden sm:flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-2xs font-medium text-text">
      <Icon name="calendar" className="h-4 w-4 text-textSecondary" />
      Mixed Scope
    </div>
  );
}

const SCOPE_ROWS: { label: string; scope: string }[] = [
  { label: "Total Leads / Assigned Leads / Converted Customers / Active Policies", scope: "All-time" },
  { label: "Disbursed Amount / Revenue Mix", scope: "This month" },
  { label: "Disbursed Trend", scope: "Last 6 months" },
  { label: "Lead Sources / Pipeline Overview / Top Employees", scope: "All-time" },
  { label: "Tasks / Recent Activities", scope: "Live" },
];

export function FiltersButton() {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="hidden sm:flex items-center gap-2 rounded-xl border border-border px-3.5 py-2 text-2xs font-medium text-text hover:bg-background transition-colors"
      >
        <Icon name="filter" className="h-4 w-4 text-textSecondary" />
        Filters
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-card border border-border rounded-card shadow-dropdown p-4 z-20 animate-fade-in">
          <p className="text-sm font-semibold text-text mb-1">Data scope</p>
          <p className="text-2xs text-textSecondary mb-3">
            Date-range filtering isn&apos;t wired up yet — here&apos;s what each section already reflects.
          </p>
          <ul className="space-y-2">
            {SCOPE_ROWS.map((row) => (
              <li key={row.label} className="flex items-start justify-between gap-3 text-2xs">
                <span className="text-text">{row.label}</span>
                <span className="shrink-0 font-semibold text-primary">{row.scope}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
