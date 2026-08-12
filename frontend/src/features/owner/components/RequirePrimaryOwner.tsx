import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { getOwnOwnerAccount } from "@/features/owner/api";

// Owner Account Management (creating/editing/deactivating a Secondary Owner) is
// Primary-Owner-only. useAuth().role can only ever say "owner" — Primary and Secondary
// share the same role — so this guard resolves the real distinction via GET /owner/me
// before rendering. The backend re-enforces this on every request regardless (see
// require_primary_owner in the backend's owner module); this guard only spares a
// Secondary Owner the round trip of clicking in and getting rejected.
export function RequirePrimaryOwner() {
  const { role, isBootstrapping } = useAuth();
  const { data: ownerAccount, isLoading } = useQuery({
    queryKey: ["owner-own-account"],
    queryFn: getOwnOwnerAccount,
    enabled: role === "owner",
  });

  if (isBootstrapping) return null;
  if (role !== "owner") return <Navigate to="/profile" replace />;
  if (isLoading || !ownerAccount) return null;
  if (ownerAccount.owner_type !== "primary") return <Navigate to="/profile" replace />;
  return <Outlet />;
}
