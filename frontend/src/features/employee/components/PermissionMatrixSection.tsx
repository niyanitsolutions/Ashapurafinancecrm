import type { Permission } from "@/features/access_control/api";
import type { ReactNode } from "react";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { applyActionToggle } from "@/features/access_control/permissionHierarchy";
import {
  DENY_PREFIX,
  MATRIX_ACTIONS,
  MODULE_DISABLED,
  MODULE_ENABLED,
  PERMISSION_MATRIX_ROWS,
  findRowPermission,
  type MatrixAction,
} from "@/features/employee/permissionMatrix";

const ACTION_LABELS: Record<MatrixAction, string> = { view: "View", create: "Create", edit: "Edit" };

// Applies one checkbox change to a working copy of `checked`, enforcing the dependency
// rule between View and Create/Edit via the shared applyActionToggle (see
// permissionHierarchy.ts). Mutates `next` in place; callers pass a fresh shallow copy of
// `checked` before applying one or more cells.
function applyCellChange(next: Record<string, Set<string>>, permission: Permission, action: MatrixAction, isChecked: boolean): void {
  next[permission.id] = applyActionToggle(next[permission.id] ?? new Set(), action, isChecked, permission.actions);
}

// Shared by CreateEmployeePage and EditEmployeePage — a controlled component; all
// checkbox state (`checked`, keyed by permission_id -> the set of checked actions for
// that row) lives in the parent page so Create can start empty and Edit can
// pre-populate from the employee's existing grants. Renders a real table at `sm:` and
// above; below that the multi-row, three-action table doesn't reflow sensibly, so it switches to
// a stacked block per module instead, sharing the same `checked`/`onChange` state.
//
// The backend independently enforces the same View-gates-Create/Edit rule
// (PermissionEngine.has_permission / set_role_permissions) — this component's version is
// UI convenience so the Owner never sees a nonsensical state in the first place, not the
// security boundary itself.
export function PermissionMatrixSection({
  permissions,
  checked,
  onChange,
}: {
  permissions: Permission[];
  checked: Record<string, Set<string>>;
  onChange: (next: Record<string, Set<string>>) => void;
}) {
  const toggleCell = (permission: Permission, action: MatrixAction) => {
    const next = { ...checked };
    const isCurrentlyChecked = (checked[permission.id] ?? new Set()).has(action);
    applyCellChange(next, permission, action, !isCurrentlyChecked);
    if (permission.node_type === "module" && action === "view" && isCurrentlyChecked) {
      for (const child of permissions.filter((candidate) => candidate.module === permission.module && candidate.node_type !== "module")) {
        const childSelection = new Set(next[child.id] ?? []);
        if ((childSelection.has("create") || childSelection.has("edit")) && !childSelection.has("view")) {
          childSelection.delete(`${DENY_PREFIX}view`);
          childSelection.add("view");
          next[child.id] = childSelection;
        }
      }
    }
    if (permission.node_type === "module" && !isCurrentlyChecked) {
      next[permission.id].delete(MODULE_DISABLED);
      next[permission.id].add(MODULE_ENABLED);
    }
    onChange(next);
  };

  const hierarchyRoots = permissions.filter((permission) => permission.node_type === "module");
  const permissionByKey = new Map(permissions.map((permission) => [`${permission.module}:${permission.resource}`, permission]));

  const effective = (permission: Permission, action: MatrixAction): boolean => {
    const selected = checked[permission.id] ?? new Set<string>();
    if (selected.has(action)) return true;
    if (selected.has(`${DENY_PREFIX}${action}`)) return false;
    if (!permission.parent_resource) return false;
    const parent = permissionByKey.get(`${permission.module}:${permission.parent_resource}`);
    return parent ? effective(parent, action) : false;
  };

  const cycleOverride = (permission: Permission, action: MatrixAction) => {
    const next = { ...checked };
    const selected = new Set(checked[permission.id] ?? []);
    const deny = `${DENY_PREFIX}${action}`;
    if (selected.has(action)) {
      selected.delete(action);
      selected.add(deny);
    } else if (selected.has(deny)) {
      selected.delete(deny);
    } else {
      selected.add(action);
      if (action === "create" || action === "edit") {
        selected.delete(`${DENY_PREFIX}view`);
        if (!effective(permission, "view")) selected.add("view");
      }
    }
    if (action === "view" && selected.has(deny)) {
      for (const dependent of ["create", "edit"] as const) {
        selected.delete(dependent);
        selected.add(`${DENY_PREFIX}${dependent}`);
      }
    }
    next[permission.id] = selected;
    onChange(next);
  };

  const toggleModule = (permission: Permission) => {
    const next = { ...checked };
    const selected = new Set(checked[permission.id] ?? []);
    const enabled = !selected.has(MODULE_ENABLED);
    selected.delete(MODULE_ENABLED);
    selected.delete(MODULE_DISABLED);
    selected.add(enabled ? MODULE_ENABLED : MODULE_DISABLED);
    next[permission.id] = selected;
    onChange(next);
  };

  const renderNode = (permission: Permission, depth: number): ReactNode => {
    const children = permissions.filter(
      (candidate) => candidate.module === permission.module && candidate.parent_resource === permission.resource,
    );
    const selected = checked[permission.id] ?? new Set<string>();
    const label = permission.label || permission.resource.replace(/_/g, " ");
    const row = (
      <div key={permission.id} className="grid grid-cols-[minmax(12rem,1fr)_repeat(3,5.5rem)] items-center border-t border-border py-2 text-sm">
        <div className="flex items-center gap-2" style={{ paddingLeft: `${depth * 1.25}rem` }}>
          {permission.node_type === "module" && (
            <input type="checkbox" aria-label={`${label} module enabled`} checked={selected.has(MODULE_ENABLED)} onChange={() => toggleModule(permission)} />
          )}
          <span className={permission.node_type === "module" ? "font-semibold" : "text-text"}>{label}</span>
        </div>
        {MATRIX_ACTIONS.map((action) => {
          if (!permission.actions.includes(action)) return <span key={action} className="text-center text-text/20">—</span>;
          if (permission.node_type === "module") {
            return <CheckboxField key={action} label={`${label} — ${ACTION_LABELS[action]}`} hideLabel className="justify-center" checked={selected.has(action)} onChange={() => toggleCell(permission, action)} />;
          }
          const state = selected.has(action) ? "Override Yes" : selected.has(`${DENY_PREFIX}${action}`) ? "Override No" : `Inherited ${effective(permission, action) ? "Yes" : "No"}`;
          return <button key={action} type="button" aria-label={`${label} ${ACTION_LABELS[action]}: ${state}`} onClick={() => cycleOverride(permission, action)} className="mx-auto rounded px-1.5 py-1 text-[10px] text-primary hover:bg-primary/10">{state}</button>;
        })}
      </div>
    );
    return <div key={permission.id}>{row}{children.map((child) => renderNode(child, depth + 1))}</div>;
  };

  if (hierarchyRoots.length > 0) {
    return (
      <div className="rounded-card border border-border bg-card p-6 shadow-card">
        <h2 className="mb-1 text-sm font-semibold text-text">Permissions</h2>
        <p className="mb-4 text-xs text-text/50">Module actions are defaults. Select a child action to cycle through inherited, explicit allow, and explicit deny.</p>
        <div className="overflow-x-auto">
          <div className="min-w-[34rem]">
            <div className="grid grid-cols-[minmax(12rem,1fr)_repeat(3,5.5rem)] text-xs font-semibold text-textSecondary">
              <span>Module / page</span>{MATRIX_ACTIONS.map((action) => <span key={action} className="text-center">{ACTION_LABELS[action]}</span>)}
            </div>
            {hierarchyRoots.map((root) => <details key={root.id} open><summary className="cursor-pointer py-1 text-xs text-textSecondary">{root.label || root.module}</summary>{renderNode(root, 0)}</details>)}
          </div>
        </div>
      </div>
    );
  }

  // "Select all" for one action column — only ever touches rows whose live Permission
  // actually supports that action (e.g. clicking "Select all Create" never tries to
  // grant Loan Management create, which doesn't exist as a real action).
  const toggleColumn = (action: MatrixAction) => {
    const applicable = PERMISSION_MATRIX_ROWS.map((row) => findRowPermission(permissions, row)).filter(
      (p): p is Permission => !!p && p.actions.includes(action)
    );
    if (applicable.length === 0) return;
    const allChecked = applicable.every((p) => (checked[p.id] ?? new Set()).has(action));
    const next = { ...checked };
    for (const permission of applicable) {
      applyCellChange(next, permission, action, !allChecked);
    }
    onChange(next);
  };

  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6">
      <h2 className="text-sm font-semibold text-text mb-1">Permissions</h2>
      <p className="text-xs text-text/50 mb-4">
        View controls access to the module. Create and Edit provide additional actions and never grant access by
        themselves. View does not mean they see every record either — e.g. granting Leads View/Create/Edit lets them
        use Leads and manage the ones they created or are assigned, not the whole company's list.
      </p>
      {permissions.length === 0 && <p className="text-sm text-text/40">Loading…</p>}

      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 pr-4 font-medium text-text">Module</th>
              {MATRIX_ACTIONS.map((action) => (
                <th key={action} className="py-2 px-2 font-medium text-text text-center">
                  <button type="button" onClick={() => toggleColumn(action)} className="text-xs text-primary hover:underline">
                    {ACTION_LABELS[action]}
                  </button>
                  <div className="text-[10px] font-normal text-text/40">Select all</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PERMISSION_MATRIX_ROWS.map((row) => {
              const permission = findRowPermission(permissions, row);
              return (
                <tr key={`${row.module}:${row.resource}`} className="border-b border-border last:border-0">
                  <td className="py-2.5 pr-4 text-text">{row.label}</td>
                  {MATRIX_ACTIONS.map((action) => {
                    const supported = permission ? permission.actions.includes(action) : false;
                    return (
                      <td key={action} className="py-2.5 px-2 text-center">
                        {supported && permission ? (
                          <CheckboxField
                            label={`${row.label} — ${ACTION_LABELS[action]}`}
                            hideLabel
                            className="justify-center"
                            checked={(checked[permission.id] ?? new Set()).has(action)}
                            onChange={() => toggleCell(permission, action)}
                          />
                        ) : (
                          <span className="text-text/20">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="sm:hidden space-y-3">
        {PERMISSION_MATRIX_ROWS.map((row) => {
          const permission = findRowPermission(permissions, row);
          const availableActions = MATRIX_ACTIONS.filter((action) => permission?.actions.includes(action));
          return (
            <div key={`${row.module}:${row.resource}`} className="border border-border rounded-lg p-3">
              <p className="text-sm font-medium text-text mb-2">{row.label}</p>
              {permission && availableActions.length > 0 ? (
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  {availableActions.map((action) => (
                    <CheckboxField
                      key={action}
                      label={ACTION_LABELS[action]}
                      checked={(checked[permission.id] ?? new Set()).has(action)}
                      onChange={() => toggleCell(permission, action)}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text/40">Not available.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
