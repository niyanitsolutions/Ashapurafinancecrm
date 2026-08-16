import { useQuery } from "@tanstack/react-query";
import { getMyPermissions } from "@/features/access_control/api";
import { useAuth } from "@/features/auth/useAuth";

// Shared, cached read of the current user's own effective view/create/edit grants
// (`GET /my-permissions`) — mirrors `useNavKeys`'s pattern (one fetch, reused across
// every page that needs it, `staleTime` matched so both refresh together). This is a
// UI-support convenience for showing/hiding buttons — the backend independently
// enforces every action regardless of what this hook returns; hiding a button here
// never substitutes for the real `require_permission` check on the corresponding route.
//
// Owner is a hard short-circuit: `can()` always returns true for an Owner session
// without ever consulting the fetched grants (which are deliberately empty for Owner —
// see MyPermissionsResponse's own docstring) — Owner navigation/actions must never be
// gated by this hook, matching "Owner remains unrestricted."
export interface PermissionsApi {
  isOwner: boolean;
  loading: boolean;
  can: (moduleResource: string, action: string) => boolean;
}

export function usePermissions(): PermissionsApi {
  const { role } = useAuth();
  const isOwner = role === "owner";
  const { data, isLoading } = useQuery({
    queryKey: ["my-permissions"],
    queryFn: getMyPermissions,
    staleTime: 60_000,
    enabled: !isOwner, // Owner never needs this — see docstring above
  });

  const can = (moduleResource: string, action: string): boolean => {
    if (isOwner) return true;
    return (data?.grants[moduleResource] ?? []).includes(action);
  };

  return { isOwner, loading: !isOwner && isLoading, can };
}
