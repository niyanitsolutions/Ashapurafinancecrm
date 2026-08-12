import { apiRequest } from "@/shared/api/client";

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

export interface NotificationsResult {
  available: boolean;
  items: Record<string, unknown>[];
  unread_count: number;
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

export function getDashboard() {
  return apiRequest<Widget[]>("/dashboard");
}

export function getNotifications() {
  return apiRequest<NotificationsResult>("/dashboard/notifications");
}

export function search(q: string) {
  return apiRequest<{ results: SearchResult[] }>(`/dashboard/search?q=${encodeURIComponent(q)}`);
}
