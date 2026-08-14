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
  // WhatsApp + MSG91 only — identifies the pre-approved provider-side template (MSG91/
  // WhatsApp Business send only these, never this CRM's own rendered body text). `body`'s
  // `{{variable}}` order is reused as the positional order for the provider template's
  // own placeholders.
  provider_template_name: string | null;
  provider_template_namespace: string | null;
  provider_template_language: string | null;
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

export interface ProviderTemplateFields {
  provider_template_name?: string;
  provider_template_namespace?: string;
  provider_template_language?: string;
}

export function createTemplate(
  payload: { name: string; channel: string; category: string; subject?: string; body: string; language?: string } & ProviderTemplateFields,
) {
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

export function updateTemplate(
  templateId: string,
  payload: { name?: string; subject?: string; body?: string; status?: string; language?: string } & ProviderTemplateFields,
) {
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

// ---------------------------------------------------------------------- Stage 3: CRM record messaging

export type CrmEntityType = "lead" | "customer";

export interface SendMessageInput {
  entity_type: CrmEntityType;
  entity_id: string;
  channel: string;
  template_id: string;
  variables?: Record<string, string>;
}

export interface SendMessageResult {
  success: boolean;
  queue_item_id: string | null;
  status: string | null;
  error: string | null;
}

export function sendCrmMessage(payload: SendMessageInput) {
  return apiRequest<SendMessageResult>("/communication/messages", { method: "POST", body: JSON.stringify(payload) });
}

export function listEntityMessages(entityType: CrmEntityType, entityId: string) {
  return apiRequest<QueueItem[]>(`/communication/messages?entity_type=${entityType}&entity_id=${entityId}`);
}

// ---------------------------------------------------------------------- Stage 3: Bulk Messaging

export interface BulkMessageJobDetail {
  id: string;
  channel: string;
  template_id: string;
  recipient_type: CrmEntityType;
  recipient_count: number;
  queued_count: number;
  skipped_count: number;
  status: string;
  created_at: string;
  pending: number;
  sent: number;
  delivered: number;
  failed: number;
}

export interface BulkMessageJobListItem {
  id: string;
  channel: string;
  template_id: string;
  recipient_type: CrmEntityType;
  recipient_count: number;
  queued_count: number;
  skipped_count: number;
  status: string;
  created_at: string;
}

export function createBulkMessageJob(payload: { channel: string; template_id: string; recipient_type: CrmEntityType; recipient_ids: string[] }) {
  return apiRequest<BulkMessageJobDetail>("/communication/bulk-messages", { method: "POST", body: JSON.stringify(payload) });
}

export async function listBulkMessageJobs(params: { page?: number; page_size?: number }): Promise<PaginatedResponse<BulkMessageJobListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<BulkMessageJobListItem[]>(`/communication/bulk-messages${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getBulkMessageJob(jobId: string) {
  return apiRequest<BulkMessageJobDetail>(`/communication/bulk-messages/${jobId}`);
}

export function listBulkMessageJobFailed(jobId: string) {
  return apiRequest<QueueItem[]>(`/communication/bulk-messages/${jobId}/failed`);
}

export function retryBulkMessageJobFailed(jobId: string) {
  return apiRequest<{ retried_count: number }>(`/communication/bulk-messages/${jobId}/retry-failed`, { method: "POST" });
}

export function cancelBulkMessageJob(jobId: string) {
  return apiRequest<BulkMessageJobDetail>(`/communication/bulk-messages/${jobId}/cancel`, { method: "POST" });
}
