import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export const GEO_ACTIVITIES = [
  { value: "lead_creation", label: "Lead Creation" },
  { value: "document_collection", label: "Document Collection" },
  { value: "customer_visit", label: "Customer Visit" },
  { value: "loan_application", label: "Loan Application" },
  { value: "insurance_application", label: "Insurance Application" },
  { value: "login", label: "Login" },
] as const;

export interface GeoFence {
  id: string;
  area_name: string;
  address: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  allowed_activities: string[];
  status: string;
  created_at: string;
  updated_at: string;
  overlaps_with: string[];
}

export interface GeoFenceListParams {
  page?: number;
  page_size?: number;
  search?: string;
  activity?: string;
  status?: string;
}

export interface GeoFenceInput {
  area_name: string;
  address: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  allowed_activities: string[];
}

export async function listGeoFences(params: GeoFenceListParams = {}): Promise<{ items: GeoFence[]; pagination: PaginationMeta | null }> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.search) qs.set("search", params.search);
  if (params.activity) qs.set("activity", params.activity);
  if (params.status) qs.set("status", params.status);
  const query = qs.toString();
  const res = await apiRequestRaw<GeoFence[]>(`/geo-fences${query ? `?${query}` : ""}`);
  return { items: res.data ?? [], pagination: res.meta?.pagination ?? null };
}

export function getGeoFence(id: string) {
  return apiRequest<GeoFence>(`/geo-fences/${id}`);
}
export function createGeoFence(payload: GeoFenceInput) {
  return apiRequest<GeoFence>("/geo-fences", { method: "POST", body: JSON.stringify(payload) });
}
export function updateGeoFence(id: string, payload: Partial<GeoFenceInput>) {
  return apiRequest<GeoFence>(`/geo-fences/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateGeoFence(id: string) {
  return apiRequest<GeoFence>(`/geo-fences/${id}/activate`, { method: "PATCH" });
}
export function deactivateGeoFence(id: string) {
  return apiRequest<GeoFence>(`/geo-fences/${id}/deactivate`, { method: "PATCH" });
}
export function deleteGeoFence(id: string) {
  return apiRequest<null>(`/geo-fences/${id}`, { method: "DELETE" });
}
