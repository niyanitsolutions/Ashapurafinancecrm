import { apiRequest } from "@/shared/api/client";
import type { DashboardFilters } from "@/features/dashboard/DashboardFiltersContext";

export interface NavItem {
  key: string;
  label: string;
  route: string;
  icon: string | null;
  order: number;
}

export interface Widget {
  key: string;
  label: string;
  category: string;
  widget_type: "metric" | "list";
  is_visible: boolean;
  order: number;
  refresh_interval_seconds: number;
  is_pinned: boolean;
  data: Record<string, unknown> | null;
}

export interface UpdateLayoutItem {
  widget_key: string;
  is_visible: boolean;
  order: number;
  refresh_interval_seconds: number;
  is_pinned: boolean;
}

export interface SearchResult {
  type: string;
  id: string;
  label: string;
  subtitle: string | null;
  route: string;
}

export function getNav() {
  return apiRequest<NavItem[]>("/dashboard/nav");
}

export function getLayout() {
  return apiRequest<Widget[]>("/dashboard/layout");
}

export function updateLayout(widgets: UpdateLayoutItem[]) {
  return apiRequest<Widget[]>("/dashboard/layout", { method: "PUT", body: JSON.stringify({ widgets }) });
}

export function getDashboard(filters: DashboardFilters) {
  const params = new URLSearchParams({ range: filters.range });
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate) params.set("end_date", filters.endDate);
  if (filters.productCategory) params.set("product_category", filters.productCategory);
  if (filters.sourceId) params.set("source_id", filters.sourceId);
  return apiRequest<Widget[]>(`/dashboard?${params.toString()}`);
}

export function search(q: string) {
  return apiRequest<{ results: SearchResult[] }>(`/dashboard/search?q=${encodeURIComponent(q)}`);
}
