import type { CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/useAuth";
import { apiRequest } from "@/shared/api/client";

export interface StatusOption { id: string; value: string; name: string; color: string; display_order: number; is_system: boolean; is_active: boolean; version: number; created_by_name: string; created_at: string; updated_at: string }
const base = "/daily-operations/follow-up-status-options";
export const listStatusOptions = () => apiRequest<StatusOption[]>(`${base}?include_archived=true`);
export const createStatusOption = (name: string, color: string, display_order = 100) => apiRequest<StatusOption>(base, {method:"POST", body:JSON.stringify({name,color,display_order})});
export const updateStatusOption = (option: StatusOption, name: string, color: string, display_order: number) => apiRequest<StatusOption>(`${base}/${option.id}`, {method:"PATCH",body:JSON.stringify({name,color,display_order,version:option.version})});
export const archiveStatusOption = (option: StatusOption, restore = false) => apiRequest<StatusOption>(`${base}/${option.id}/${restore?"restore":"archive"}`, {method:"POST",body:JSON.stringify({version:option.version})});
export function useStatusOptions(enabled = true, live = false) {
  const {userId} = useAuth();
  return useQuery({queryKey:["daily-follow-up-status-options",userId],queryFn:listStatusOptions,enabled,staleTime:3000,refetchInterval:live?5000:false,refetchOnWindowFocus:true});
}

export function contrastText(hex:string): string {
  const rgb=hex.slice(1).match(/.{2}/g)?.map(v=>parseInt(v,16)/255)??[1,1,1];
  const linear=rgb.map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
  return .2126*linear[0]+.7152*linear[1]+.0722*linear[2]>.179?"#000000":"#FFFFFF";
}
export function statusRowStyle(value:string, options:StatusOption[]):CSSProperties|undefined {
  const color=options.find(row=>row.value===value)?.color;
  return color&&/^#[0-9A-Fa-f]{6}$/.test(color)?{backgroundColor:color,color:contrastText(color)}:undefined;
}
