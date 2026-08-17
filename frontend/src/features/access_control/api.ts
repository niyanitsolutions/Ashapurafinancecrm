import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface Role {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Permission {
  id: string;
  module: string;
  resource: string;
  actions: string[];
  label: string | null;
}

export interface RolePermissionGrant {
  id: string;
  role_id: string;
  permission_id: string;
  module: string;
  resource: string;
  granted_actions: string[];
  department_ids: string[] | null;
  branch_ids: string[] | null;
}

export interface EmployeeRoleAssignment {
  id: string;
  employee_id: string;
  role_id: string;
  role_name: string;
}

export interface TemporaryAccessGrant {
  permission_id: string;
  module: string;
  resource: string;
  actions: string[];
}

export interface TemporaryAccess {
  id: string;
  employee_id: string;
  grants: TemporaryAccessGrant[];
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  reason: string;
  status: string;
}

export interface GeoException {
  id: string;
  employee_id: string;
  // No location fields — a GeoException is a temporary BYPASS of the employee's
  // applicable Geo Fence(s) during the given window, never a second, competing
  // location restriction of its own.
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  reason: string;
  status: string;
  // null = applies to every enforced activity ("All Activities"). A specific value
  // (e.g. "login") restricts the bypass to only that one activity.
  activity: string | null;
}

export const PERMISSION_ACTIONS = [
  "view", "create", "edit", "delete", "assign", "approve", "reject",
  "export", "import", "upload", "download", "print", "share",
] as const;

// ---- roles ----

export function listRoles() {
  return apiRequest<Role[]>("/roles");
}
export function getRole(roleId: string) {
  return apiRequest<Role>(`/roles/${roleId}`);
}
export function createRole(name: string, description?: string) {
  return apiRequest<Role>("/roles", { method: "POST", body: JSON.stringify({ name, description }) });
}
export function updateRole(roleId: string, payload: { name?: string; description?: string }) {
  return apiRequest<Role>(`/roles/${roleId}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateRole(roleId: string) {
  return apiRequest<Role>(`/roles/${roleId}/activate`, { method: "PATCH" });
}
export function deactivateRole(roleId: string) {
  return apiRequest<Role>(`/roles/${roleId}/deactivate`, { method: "PATCH" });
}
export function duplicateRole(roleId: string, newName: string) {
  return apiRequest<Role>(`/roles/${roleId}/duplicate`, { method: "POST", body: JSON.stringify({ new_name: newName }) });
}

// ---- permission catalog ----

export function listPermissions() {
  return apiRequest<Permission[]>("/permissions");
}
export function createPermission(module: string, resource: string, actions: string[], label?: string) {
  return apiRequest<Permission>("/permissions", { method: "POST", body: JSON.stringify({ module, resource, actions, label }) });
}

// ---- permission matrix ----

export function getRolePermissions(roleId: string) {
  return apiRequest<RolePermissionGrant[]>(`/roles/${roleId}/permissions`);
}

export interface RolePermissionGrantInput {
  permission_id: string;
  granted_actions: string[];
  department_ids?: string[] | null;
  branch_ids?: string[] | null;
}

export function setRolePermissions(roleId: string, grants: RolePermissionGrantInput[]) {
  return apiRequest<RolePermissionGrant[]>(`/roles/${roleId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ grants }),
  });
}

// ---- employee <-> role ----

export function assignRole(roleId: string, employeeId: string) {
  return apiRequest<EmployeeRoleAssignment>(`/roles/${roleId}/assign`, {
    method: "POST",
    body: JSON.stringify({ employee_id: employeeId }),
  });
}
export function removeRole(roleId: string, employeeId: string) {
  return apiRequest<null>(`/roles/${roleId}/remove`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) });
}
export function listEmployeeRoles(employeeId: string) {
  return apiRequest<EmployeeRoleAssignment[]>(`/employees/${employeeId}/roles`);
}

// ---- temporary access ----

export interface CreateTemporaryAccessInput {
  employee_id: string;
  grants: { permission_id: string; actions: string[] }[];
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  reason: string;
}

export function listTemporaryAccess(employeeId?: string) {
  const qs = employeeId ? `?employee_id=${employeeId}` : "";
  return apiRequest<TemporaryAccess[]>(`/temporary-access${qs}`);
}
export function createTemporaryAccess(payload: CreateTemporaryAccessInput) {
  return apiRequest<TemporaryAccess>("/temporary-access", { method: "POST", body: JSON.stringify(payload) });
}
export function revokeTemporaryAccess(id: string) {
  return apiRequest<TemporaryAccess>(`/temporary-access/${id}/revoke`, { method: "POST" });
}

// ---- geo exceptions ----

export interface CreateGeoExceptionInput {
  employee_id: string;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  reason: string;
  // Omitted/undefined = applies to every enforced activity ("All Activities").
  activity?: string;
}

export interface GeoExceptionListParams {
  employeeId?: string;
  page?: number;
  page_size?: number;
}

export async function listGeoExceptions(
  params: GeoExceptionListParams = {}
): Promise<{ items: GeoException[]; pagination: PaginationMeta | null }> {
  const qs = new URLSearchParams();
  if (params.employeeId) qs.set("employee_id", params.employeeId);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString();
  const res = await apiRequestRaw<GeoException[]>(`/geo-exceptions${query ? `?${query}` : ""}`);
  return { items: res.data ?? [], pagination: res.meta?.pagination ?? null };
}
export function createGeoException(payload: CreateGeoExceptionInput) {
  return apiRequest<GeoException>("/geo-exceptions", { method: "POST", body: JSON.stringify(payload) });
}
export function revokeGeoException(id: string) {
  return apiRequest<GeoException>(`/geo-exceptions/${id}/revoke`, { method: "POST" });
}

// ---- my-permissions (UI support) ----

export interface MyPermissions {
  // "module:resource" -> granted actions, e.g. { "leads:leads": ["view", "create"] }.
  // Empty for Owner — callers should short-circuit on role === "owner" before ever
  // consulting this, never treat an empty object as "no access" for an Owner session.
  grants: Record<string, string[]>;
}

export function getMyPermissions() {
  return apiRequest<MyPermissions>("/my-permissions");
}
