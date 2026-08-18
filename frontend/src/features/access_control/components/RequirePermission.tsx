import { Navigate, Outlet } from "react-router-dom";
import { usePermissions } from "@/features/access_control/usePermissions";

// Route guard for the one class of route this CRM's permission model requires blocked
// at the router level, not just via a hidden button: a Create/Edit route reached by
// direct URL/bookmark with only View granted (View must never imply Create/Edit — see
// PermissionEngine.has_permission). Most permission-gated routes deliberately rely on
// the backend 403 + hidden buttons instead (see router.tsx's inline comments) — this
// guard is only for routes with no other client-side signal blocking entry, e.g.
// /leads/new, which otherwise renders the full Create Lead form before the user ever
// calls the create API.
export function RequirePermission({ module, resource, action, redirectTo }: { module: string; resource: string; action: string; redirectTo: string }) {
  const { can, loading } = usePermissions();

  if (loading) {
    return null;
  }
  if (!can(`${module}:${resource}`, action)) {
    return <Navigate to={redirectTo} replace />;
  }
  return <Outlet />;
}
