import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";

export interface InterestOption { id: string; name: string; is_active: boolean; version: number; created_by_name: string; created_at: string; updated_at: string }
const base = "/daily-operations/interest-options";
export const listInterestOptions = () => apiRequest<InterestOption[]>(`${base}?include_archived=true`);
export const createInterestOption = (name: string) => apiRequest<InterestOption>(base, {method:"POST", body:JSON.stringify({name})});
export const renameInterestOption = (option: InterestOption, name: string) => apiRequest<InterestOption>(`${base}/${option.id}`, {method:"PATCH",body:JSON.stringify({name,version:option.version})});
export const archiveInterestOption = (option: InterestOption, restore = false) => apiRequest<InterestOption>(`${base}/${option.id}/${restore?"restore":"archive"}`, {method:"POST",body:JSON.stringify({version:option.version})});
export function useInterestOptions(enabled = true, live = false) {
  const {userId} = useAuth();
  return useQuery({queryKey:["daily-interest-options",userId],queryFn:listInterestOptions,enabled,staleTime:3000,refetchInterval:live?5000:false,refetchOnWindowFocus:true});
}
