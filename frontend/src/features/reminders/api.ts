import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  assigned_to: string;
  assigned_to_name: string | null;
  assigned_by: string;
  due_at: string;
  status: string;
  completed_at: string | null;
  owner_escalated: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReminderRule {
  id: string;
  rule_type: string;
  label: string;
  status: string;
  case_type: string | null;
  eligible_after_days: number | null;
  // A rule can define multiple trigger points (e.g. 30/15/7/1 days before eligibility) —
  // each fires its own, independently-tracked reminder.
  notify_before_days: number[] | null;
  notify_before_minutes: number[] | null;
  escalation_repeat_minutes: number | null;
  escalation_max_repeats: number | null;
  created_at: string;
  updated_at: string;
}

export interface AppNotification {
  id: string;
  notification_type: string;
  category: string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  status: string;
  created_at: string;
  read_at: string | null;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

// ---- Tasks ----

export function createTask(payload: { title: string; description?: string; assigned_to: string; due_at: string }) {
  return apiRequest<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) });
}

export async function listTasks(params: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<Task>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<Task[]>(`/tasks${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function completeTask(taskId: string) {
  return apiRequest<Task>(`/tasks/${taskId}/complete`, { method: "POST" });
}

// ---- Reminder Rules ----

export function listReminderRules() {
  return apiRequest<ReminderRule[]>("/reminder-rules");
}

export function createReminderRule(payload: {
  rule_type: string; label: string; case_type?: string; eligible_after_days?: number; notify_before_days?: number[];
  notify_before_minutes?: number[]; escalation_repeat_minutes?: number; escalation_max_repeats?: number;
}) {
  return apiRequest<ReminderRule>("/reminder-rules", { method: "POST", body: JSON.stringify(payload) });
}

export function updateReminderRule(ruleId: string, payload: Record<string, unknown>) {
  return apiRequest<ReminderRule>(`/reminder-rules/${ruleId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function activateReminderRule(ruleId: string) {
  return apiRequest<ReminderRule>(`/reminder-rules/${ruleId}/activate`, { method: "PATCH" });
}

export function deactivateReminderRule(ruleId: string) {
  return apiRequest<ReminderRule>(`/reminder-rules/${ruleId}/deactivate`, { method: "PATCH" });
}

// ---- Notifications ----

export async function listNotifications(params: { page?: number; page_size?: number; status?: string; category?: string }): Promise<PaginatedResponse<AppNotification>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<AppNotification[]>(`/notifications${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function markNotificationRead(notificationId: string) {
  return apiRequest<AppNotification>(`/notifications/${notificationId}/read`, { method: "POST" });
}

export function archiveNotification(notificationId: string) {
  return apiRequest<AppNotification>(`/notifications/${notificationId}/archive`, { method: "POST" });
}

export function dismissNotification(notificationId: string) {
  return apiRequest<AppNotification>(`/notifications/${notificationId}/dismiss`, { method: "POST" });
}
