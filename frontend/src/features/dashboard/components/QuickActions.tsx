import { Link } from "react-router-dom";
import { hasNavAccess } from "@/components/layout/navAccess";
import { useNavKeys } from "@/components/layout/useNavKeys";

// Phase 4 — Quick Actions are gated by the exact same permission signal as the
// Sidebar/Dashboard widgets: the live, permission-filtered `nav_items` key set
// (`useNavKeys`), never a second, separate check. If "Leads" disappears from the
// sidebar, "Create Lead" disappears from here too, automatically, no refresh needed.
//
// Only actions that correspond to a real, standalone entry point in this CRM are
// listed. "Add Customer" (Customers arise only from Lead conversion / self-registration
// — there's no direct staff "create customer" flow, Module 6B's own capability list)
// and "Create Loan/Insurance Case" (cases are created automatically, lazily, once an
// Application is submitted — decision 058, never a manual action) were deliberately
// left out rather than linked to something that doesn't exist.
const QUICK_ACTIONS: { label: string; to: string; matchKey: string | string[] }[] = [
  { label: "Create Lead", to: "/leads/new", matchKey: "leads" },
  { label: "Generate Secure Link", to: "/leads", matchKey: "leads" },
  { label: "Create Task", to: "/tasks", matchKey: "tasks" },
];

export function QuickActions() {
  const navKeys = useNavKeys();
  const visible = QUICK_ACTIONS.filter((action) => hasNavAccess(navKeys, action.matchKey));

  if (visible.length === 0) return null;

  return (
    <div className="mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-text/40 mb-2">Quick Actions</h2>
      <div className="flex flex-wrap gap-3">
        {visible.map((action) => (
          <Link
            key={action.label}
            to={action.to}
            className="rounded-lg bg-primary text-white text-sm font-medium py-2 px-4 hover:bg-primary-light transition-colors"
          >
            {action.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
