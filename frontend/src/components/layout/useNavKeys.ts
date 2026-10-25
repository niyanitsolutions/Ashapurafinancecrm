import { useQuery } from "@tanstack/react-query";
import { getNav } from "@/features/dashboard/api";
import { useAuth } from "@/features/auth/useAuth";

// Shared, cached read of the permission-filtered `nav_items` catalog (`GET
// /dashboard/nav` — see docs/decisions/DECISIONS.md #033). Sidebar and any
// in-page ModuleTabs both call this so the nav list is fetched once and
// reused, not re-requested per page. Returns undefined while loading (never
// an empty Set), so callers can tell "still loading" apart from "no access".
export function useNavKeys(): Set<string> | undefined {
  const { userId } = useAuth();
  const { data, isError } = useQuery({
    // Never reuse an Owner's navigation after an Employee signs in in the same tab.
    queryKey: ["dashboard-nav", userId],
    queryFn: getNav,
    staleTime: 60_000,
    enabled: !!userId,
  });
  if (isError) return new Set();
  return data ? new Set(data.map((item) => item.key)) : undefined;
}
