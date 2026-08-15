import type { Permission } from "@/features/access_control/api";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { MATRIX_ACTIONS, PERMISSION_MATRIX_ROWS, findRowPermission, type MatrixAction } from "@/features/employee/permissionMatrix";

const ACTION_LABELS: Record<MatrixAction, string> = { view: "View", create: "Create", edit: "Edit" };

// Applies one checkbox change to a working copy of `checked`, enforcing the dependency
// rule between View and Create/Edit: checking Create or Edit implies View (an action
// can't be useful without access), and unchecking View clears Create/Edit for that same
// row (they never grant access on their own). Mutates `next` in place; callers pass a
// fresh shallow copy of `checked` before applying one or more cells.
function applyCellChange(next: Record<string, Set<string>>, permission: Permission, action: MatrixAction, isChecked: boolean): void {
  const current = new Set(next[permission.id] ?? []);
  if (isChecked) {
    current.add(action);
    if ((action === "create" || action === "edit") && permission.actions.includes("view")) {
      current.add("view");
    }
  } else {
    current.delete(action);
    if (action === "view") {
      current.delete("create");
      current.delete("edit");
    }
  }
  next[permission.id] = current;
}

// Shared by CreateEmployeePage and EditEmployeePage — a controlled component; all
// checkbox state (`checked`, keyed by permission_id -> the set of checked actions for
// that row) lives in the parent page so Create can start empty and Edit can
// pre-populate from the employee's existing grants. Renders a real table at `sm:` and
// above; below that an 8-row x 3-column table doesn't reflow sensibly, so it switches to
// a stacked block per module instead, sharing the same `checked`/`onChange` state.
//
// Backend enforcement is independent of this UI convenience: `require_permission`
// checks each action (view/create/edit) completely separately server-side regardless of
// what the frontend allowed to be checked together — this component's View-gates-
// Create/Edit behavior only prevents the Owner from configuring a nonsensical state in
// the first place, it is never itself a security boundary.
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
    onChange(next);
  };

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
