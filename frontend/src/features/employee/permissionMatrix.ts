import type { Permission, RolePermissionGrantInput } from "@/features/access_control/api";

// The Owner-facing Permissions matrix — one row per business area, View/Create/Edit
// checkboxes per row, each backed directly by the existing Access Control permission
// catalog (Role/RolePermission/EmployeeRole/Permission, PermissionEngine). Replaces the
// old BUSINESS_MODULES + SHARED_RESOURCES design (businessModules.ts, removed), which
// only exposed Loan Management/Insurance Management as checkboxes and silently
// auto-granted full, non-configurable Leads + Tasks access to any employee with either
// one checked — the real source of the "confusing relationship" between an employee's
// other settings and their Lead access. Every row here is independently controllable;
// nothing here reads or writes `Employee.product_ids` ("Product Specialization"), which
// stays a wholly separate, permission-free field.
export interface MatrixRow {
  module: string; // Permission.module
  resource: string; // Permission.resource
  label: string;
}

// A future business area (Credit Cards, Mutual Funds, ...) is one entry here plus its
// own Permission catalog row — no change to this file's logic or the rendering
// component. Deliberately doesn't list areas with no backing feature yet.
export const PERMISSION_MATRIX_ROWS: MatrixRow[] = [
  { module: "leads", resource: "leads", label: "Leads" },
  { module: "customer", resource: "customers", label: "Customers" },
  { module: "reminders", resource: "tasks", label: "Tasks" },
  { module: "loan_management", resource: "applications", label: "Loan Management" },
  { module: "insurance_management", resource: "applications", label: "Insurance Management" },
  { module: "referral_partner_management", resource: "partners", label: "Referral Partners" },
  { module: "reporting", resource: "reports", label: "Reports & Analytics" },
  { module: "communication", resource: "templates", label: "Message Center" },
];

// The basic matrix only ever offers these three actions as checkboxes — Assign/Approve/
// Reject/Export/etc. stay in the full Roles & Permissions screen, matching the old UI's
// "view/assign are automatic, capabilities are extra" convention, just narrowed to a
// fixed 3-action set shown identically for every row instead of a per-module capability
// list. Not every row's live Permission.actions includes all three (e.g. Loan/Insurance
// Cases have no "create" action, Reports has no "create"/"edit") — callers must check
// against the row's own Permission before rendering or granting a cell.
export const MATRIX_ACTIONS = ["view", "create", "edit"] as const;
export type MatrixAction = (typeof MATRIX_ACTIONS)[number];

export function findRowPermission(permissions: Permission[], row: MatrixRow): Permission | undefined {
  return permissions.find((p) => p.module === row.module && p.resource === row.resource);
}

// Builds the grants to send to `setRolePermissions` from the matrix's checked state.
// `checked` is keyed by permission_id -> the set of checked actions for that row. A row
// with nothing checked contributes no grant at all (same as before). Filters against
// the row's live `Permission.actions` so a nonexistent action for that row (e.g. "create"
// on Loan Management) can never be silently included even if UI state somehow set it.
export function buildMatrixGrants(permissions: Permission[], checked: Record<string, Set<string>>): RolePermissionGrantInput[] {
  const grants: RolePermissionGrantInput[] = [];
  for (const row of PERMISSION_MATRIX_ROWS) {
    const permission = findRowPermission(permissions, row);
    if (!permission) continue;
    const checkedForRow = checked[permission.id] ?? new Set<string>();
    const actions = MATRIX_ACTIONS.filter((action) => permission.actions.includes(action) && checkedForRow.has(action));
    if (actions.length === 0) continue;
    grants.push({ permission_id: permission.id, granted_actions: actions });
  }
  return grants;
}
