import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { Icon, type IconName } from "@/theme/icons";

// Only entities with a real, existing create route/flow are listed here — Customers,
// Loan/Insurance Cases, and Referral Partners have no dedicated staff "create" screen
// today (Customers/Cases are created via Lead conversion; see docs/KNOWN_LIMITATIONS.md),
// so adding them here would be a dead/fake action, not a real shortcut.
const ITEMS: { label: string; to: string; icon: IconName; ownerOnly?: boolean }[] = [
  { label: "Lead", to: "/leads/new", icon: "leads" },
  // Task assignment is Owner-only today (TaskListPage's own CreateTaskForm is gated the
  // same way) — matched here, not a new restriction.
  { label: "Task", to: "/tasks", icon: "tasks", ownerOnly: true },
  { label: "Employee", to: "/employees/new", icon: "employees", ownerOnly: true },
];

export function QuickAddMenu() {
  const { role } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const items = ITEMS.filter((item) => !item.ownerOnly || role === "owner");

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg bg-primary text-white text-sm font-medium py-2 px-3.5 hover:bg-primary-light transition-colors"
      >
        <Icon name="plus" className="h-4 w-4" />
        <span className="hidden sm:inline">Add New</span>
        <Icon name="chevron-down" className="h-3.5 w-3.5" />
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-44 bg-card border border-border rounded-card shadow-card py-1 text-sm z-20">
          {items.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-2 px-4 py-2 hover:bg-background text-text"
            >
              <Icon name={item.icon} className="h-4 w-4 text-text/50" />
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
