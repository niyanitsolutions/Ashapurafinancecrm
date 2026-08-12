import type { Permission, RolePermissionGrantInput } from "@/features/access_control/api";

// The Owner-facing "Business Modules" concept — a business-friendly layer over the
// existing, unmodified Access Control permission catalog (Role/RolePermission/
// EmployeeRole/Permission, PermissionEngine). An Owner never sees "Role," "Permission,"
// "Grant," "Resource," or "Action" here — only which business area an employee works in
// and a short list of business-meaningful capabilities. See CreateEmployeePage.tsx /
// EditEmployeePage.tsx for where this renders.
export interface BusinessModuleDefinition {
  key: string; // Permission.module for this module's own resource
  resource: string; // Permission.resource
  label: string;
  description: string;
}

// The two real business modules today. A future module (Credit Cards, Mutual Funds, Gold
// Loans, Vehicle Finance, ...) is one entry here plus its own Permission catalog row
// (module="credit_cards", resource="applications", actions=[...]) created once via Roles
// & Permissions — no change to this file's logic, CreateEmployeePage, EditEmployeePage,
// or the PermissionEngine. Deliberately doesn't list modules with no backing feature yet
// (Credit Cards/Mutual Funds/etc.) — an unchecked box that grants nothing would be worse
// than not offering it.
export const BUSINESS_MODULES: BusinessModuleDefinition[] = [
  {
    key: "loan_management",
    resource: "applications",
    label: "Loan Management",
    description: "Assigned loan leads, loan cases, and loan tasks — this employee's own records only.",
  },
  {
    key: "insurance_management",
    resource: "applications",
    label: "Insurance Management",
    description: "Assigned insurance leads, insurance cases, and insurance tasks — this employee's own records only.",
  },
];

// Cross-cutting record types every Business Module grants FULL, non-configurable access
// to — Leads/Tasks aren't modules themselves, they're shared across whichever module(s)
// an employee has. No checkboxes for these: selecting any module is enough. "view" is
// included here too — it's what makes View "automatic" instead of a checkbox the Owner
// has to remember to tick.
const SHARED_RESOURCES: { module: string; resource: string; actions: string[] }[] = [
  { module: "leads", resource: "leads", actions: ["view", "create", "edit", "export"] },
  { module: "reminders", resource: "tasks", actions: ["view", "create", "edit"] },
];

// Generic action-code -> business verb, reused across every module (not hardcoded per
// module) — combined with the live Permission's own `label` (e.g. "Loan Cases") to build
// checkbox text like "Approve Loan Cases" without hand-authoring copy per module. "view"
// and "assign" never appear here — View is automatic, Assign is Owner/Admin-only.
const ACTION_VERBS: Record<string, string> = {
  create: "Create",
  edit: "Edit",
  export: "Export",
  delete: "Delete",
  approve: "Approve",
  reject: "Reject",
  import: "Import",
  upload: "Upload",
  download: "Download",
  print: "Print",
  share: "Share",
};

export function findModulePermission(permissions: Permission[], module: BusinessModuleDefinition): Permission | undefined {
  return permissions.find((p) => p.module === module.key && p.resource === module.resource);
}

// The "Optional Capabilities" checkbox list for one selected module — that module's own
// real actions, minus view/assign, labeled in business language.
export function capabilityOptions(permission: Permission): { action: string; label: string }[] {
  return permission.actions
    .filter((action) => action !== "view" && action !== "assign")
    .map((action) => ({ action, label: `${ACTION_VERBS[action] ?? action} ${permission.label ?? permission.resource}` }));
}

// Builds the final grants to send to `setRolePermissions` from which modules are checked
// and which optional capabilities were checked under each. `view` is always included for
// every resource touched; `assign` is never included anywhere.
export function buildModuleGrants(
  permissions: Permission[],
  selectedModuleKeys: Set<string>,
  checkedCapabilities: Record<string, Set<string>>, // permission_id -> checked actions
): RolePermissionGrantInput[] {
  if (selectedModuleKeys.size === 0) return [];

  const grants: RolePermissionGrantInput[] = [];

  for (const module of BUSINESS_MODULES) {
    if (!selectedModuleKeys.has(module.key)) continue;
    const permission = findModulePermission(permissions, module);
    if (!permission) continue;
    const checked = checkedCapabilities[permission.id] ?? new Set<string>();
    grants.push({ permission_id: permission.id, granted_actions: ["view", ...checked] });
  }

  for (const shared of SHARED_RESOURCES) {
    const permission = permissions.find((p) => p.module === shared.module && p.resource === shared.resource);
    if (!permission) continue;
    grants.push({ permission_id: permission.id, granted_actions: [...shared.actions] });
  }

  return grants;
}
