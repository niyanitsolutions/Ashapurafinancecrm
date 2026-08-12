import { useQuery } from "@tanstack/react-query";
import { getProfile } from "@/features/auth/api";

// Shared, cached read of `/auth/profile` — Topbar and the Sidebar's bottom profile card
// both need the mobile/role for display; React Query's cache (same queryKey) means only
// one network request fires even though both mount it, rather than each calling
// `getProfile()` in its own `useEffect` (the previous Topbar-only pattern).
export function useProfile() {
  return useQuery({
    queryKey: ["auth-profile"],
    queryFn: getProfile,
    staleTime: 60_000,
  });
}
