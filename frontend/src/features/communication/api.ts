import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface CommunicationTemplate {
  id: string;
  name: string;
  channel: string;
  category: string;
  subject: string | null;
  body: string;
  variables: string[];
  language: string;
  status: string;
  created_at: string;
}

export interface QueueItem {
  id: string;
  channel: string;
  recipient: string;
  template_id: string;
  variables: Record<string, string>;
  rendered_subject: string | null;
  rendered_body: string;
  status: string;
  provider_message_id: string | null;
  retry_count: number;
  next_retry_at: string | null;
  error_detail: string | null;
  business_event: string | null;
  entity_type: string | null;
  entity_id: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
}

export interface HistoryItem {
  id: string;
  queue_item_id: string;
  channel: string;
  provider: string;
  recipient: string;
  template_id: string;
  template_name: string;
  variables: Record<string, string>;
  status: string;
  error: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  retry_count: number;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

export function createTemplate(payload: { name: string; channel: string; category: string; subject?: string; body: string; language?: string }) {
  return apiRequest<CommunicationTemplate>("/communication/templates", { method: "POST", body: JSON.stringify(payload) });
}

export function listTemplates(params: { channel?: string; category?: string } = {}) {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) usp.set(key, value);
  }
  const qs = usp.toString();
  return apiRequest<CommunicationTemplate[]>(`/communication/templates${qs ? `?${qs}` : ""}`);
}

export function updateTemplate(templateId: string, payload: { name?: string; subject?: string; body?: string; status?: string; language?: string }) {
  return apiRequest<CommunicationTemplate>(`/communication/templates/${templateId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listQueue(params: { page?: number; page_size?: number; status?: string; channel?: string }): Promise<PaginatedResponse<QueueItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<QueueItem[]>(`/communication/queue${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function retryQueueItem(queueItemId: string) {
  return apiRequest<QueueItem>(`/communication/queue/${queueItemId}/retry`, { method: "POST" });
}

export async function listHistory(params: { page?: number; page_size?: number; status?: string; channel?: string }): Promise<PaginatedResponse<HistoryItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<HistoryItem[]>(`/communication/history${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}
