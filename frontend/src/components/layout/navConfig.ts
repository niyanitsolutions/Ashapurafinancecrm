import type { IconName } from "@/theme/icons";

// The DB-driven `nav_items` catalog (`GET /dashboard/nav`, permission-filtered
// server-side — see docs/decisions/DECISIONS.md #033) remains the single source of
// truth for WHICH items a signed-in user is allowed to see: this file only adds visual
// grouping/icons/ordering on top of it, and never overrides its access decision.
//
// Each leaf's `matchKey` must be a real `nav_items.key` — a leaf only renders if that
// key is present in the live API response. Several leaves intentionally share one
// matchKey (e.g. "Disbursed"/"Rejected" both gate on "loan_cases") because they're
// filtered views of the exact same permission-gated route, not a separate page.

export interface NavLeaf {
  label: string;
  to: string;
  icon: IconName;
  /** A leaf renders if ANY of these keys is present in the live nav response —
   * an array is used for a single sidebar entry that consolidates what used to
   * be several separately-gated leaves (e.g. Settings = "settings" or
   * "reminder_rules"), so collapsing them into one link never hides a page a
   * role could already see. */
  matchKey: string | string[];
  /** Only match this leaf as "active" on an exact pathname+search match, not by prefix
   * (used when several leaves share the same base route with different query strings). */
  exact?: boolean;
  /** Extra pathname prefixes (besides `to` itself) that should also count as this leaf
   * being active — for a consolidated module whose tabs live under several unrelated
   * URL prefixes (e.g. Administration = /employees, /roles, /settings/departments, ...),
   * so the sidebar stays highlighted no matter which of the module's tabs is open. */
  activePrefixes?: string[];
  /** Alternate destination used when the signed-in user isn't an Owner. A few
   * consolidated entries (Settings, Administration) bundle tabs with mixed gating —
   * most require the Owner role, but one or two (Reminder Rules, Lead Capture Log)
   * are permission-gated only, reachable by any staff member with that permission.
   * Without this, an employee granted just that one permission would see the
   * sidebar entry but land on an Owner-only route and get redirected away. */
  employeeTo?: string;
  /** No leaf currently sets this — every shipped module has a real route. Kept as
   * available infrastructure for a genuinely new, not-yet-built module: a leaf marked
   * true renders as a disabled, non-navigating row with a "Soon" badge instead of being
   * omitted outright. Drop the flag from any leaf the moment it ships a real route. */
  comingSoon?: boolean;
}

export interface NavSection {
  label: string | null;
  items: NavLeaf[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: null,
    items: [{ label: "Dashboard", to: "/", icon: "dashboard", matchKey: "dashboard" }],
  },
  {
    label: "CRM",
    items: [
      { label: "Leads", to: "/leads", icon: "leads", matchKey: "leads" },
      {
        label: "Customers",
        to: "/customers",
        icon: "customers",
        matchKey: ["customers", "applications"],
        activePrefixes: ["/applications"],
      },
      { label: "Tasks", to: "/tasks", icon: "tasks", matchKey: "tasks" },
    ],
  },
  {
    label: null,
    items: [{ label: "Loan Management", to: "/loan-management", icon: "loan", matchKey: "loan_cases" }],
  },
  {
    label: null,
    items: [{ label: "Insurance Management", to: "/insurance-management", icon: "insurance", matchKey: "insurance_cases" }],
  },
  {
    label: null,
    items: [
      {
        label: "Referral Partners",
        to: "/referral-partners",
        icon: "referral",
        matchKey: ["referral_partners", "commission_rules", "commission_ledger"],
        activePrefixes: ["/referral-partners", "/commission-rules", "/commission-ledger"],
      },
    ],
  },
  {
    label: null,
    items: [
      {
        label: "Reports & Analytics",
        to: "/reports",
        icon: "reports",
        matchKey: ["reports", "scheduled_reports"],
        activePrefixes: ["/reports", "/scheduled-reports"],
      },
    ],
  },
  {
    label: null,
    items: [{ label: "Message Center", to: "/communication", icon: "communication", matchKey: "communication" }],
  },
  {
    label: "API Connections",
    items: [{ label: "Connections", to: "/integrations", icon: "integrations", matchKey: "integrations" }],
  },
  {
    label: null,
    items: [
      {
        label: "Administration",
        to: "/employees",
        icon: "shield-check",
        matchKey: ["employees", "roles", "temporary_access", "geo_exceptions", "lead_capture"],
        activePrefixes: ["/employees", "/roles", "/settings/departments", "/settings/designations", "/temporary-access", "/geo-exceptions", "/lead-capture"],
        employeeTo: "/lead-capture",
      },
    ],
  },
  {
    label: null,
    items: [{ label: "Settings", to: "/settings", icon: "settings", matchKey: ["settings", "reminder_rules"], employeeTo: "/reminder-rules" }],
  },
  {
    label: null,
    // Server-gated to the Primary Owner only (see RequirePrimaryOwner + backend's
    // require_primary_owner) — a Secondary Owner who somehow sees this link (e.g. a
    // stale cached nav response) is redirected away rather than reaching the page.
    items: [{ label: "Owner Management", to: "/owner-accounts", icon: "shield-check", matchKey: "owner_accounts" }],
  },
];
