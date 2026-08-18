// Shared View->Create/Edit dependency rule for every permission editor (Employee's
// 8-row PermissionMatrixSection and the Role-level PermissionMatrixPage): Create/Edit
// never grant access on their own, so checking either implies View, and unchecking View
// clears both. The backend (PermissionEngine.has_permission / set_role_permissions)
// enforces the same rule independently — this is UI convenience, not the security
// boundary, but keeping both editors and the initial load consistent with what the
// backend will actually allow avoids a confusing "saved fine, does nothing" or a
// surprise 422.

export function applyActionToggle(
  current: Set<string>,
  action: string,
  isChecked: boolean,
  availableActions: readonly string[]
): Set<string> {
  const next = new Set(current);
  if (isChecked) {
    next.add(action);
    if ((action === "create" || action === "edit") && availableActions.includes("view")) {
      next.add("view");
    }
  } else {
    next.delete(action);
    if (action === "view") {
      next.delete("create");
      next.delete("edit");
    }
  }
  return next;
}

// Applied to actions loaded from the backend, so pre-existing data that was saved
// before this rule existed (or saved through a path that didn't enforce it) renders
// consistently with what the backend will actually authorize.
export function sanitizeGrantedActions(actions: Iterable<string>, availableActions: readonly string[]): Set<string> {
  const next = new Set(actions);
  if (availableActions.includes("view") && !next.has("view")) {
    next.delete("create");
    next.delete("edit");
  }
  return next;
}
