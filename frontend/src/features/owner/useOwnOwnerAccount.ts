import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { getOwnOwnerAccount } from "@/features/owner/api";

// Distinguishes Primary vs Secondary Owner client-side — useAuth().role is always just
// "owner" for both (see RequirePrimaryOwner's own comment on this). Same query
// key/config as that guard, so React Query dedupes to a single request when both this
// hook and RequirePrimaryOwner are mounted at once.
export function useOwnOwnerAccount() {
  const { role } = useAuth();
  return useQuery({
    queryKey: ["owner-own-account"],
    queryFn: getOwnOwnerAccount,
    enabled: role === "owner",
    staleTime: 60_000,
  });
}
