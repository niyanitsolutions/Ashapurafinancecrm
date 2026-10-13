import { apiRequest } from "@/shared/api/client";

export interface VoiceCall {
  id: string; version: number; status: string; direction: string; contact_label: string;
  created_at: string; duration_seconds: number; recording_status: string;
  deadline_at: string; transfer_outcome: string | null;
  timeline: { state: string; at: string; reason: string }[];
}
export interface ProviderReadiness {
  telephony: string; conversation_ai: string; blockers: string[]; validated_languages: string[];
  selected_provider?: string; sandbox?: string;
}
export interface VoiceDashboard {
  metrics: Record<string, number>; data_mode: string; estimated_cost: number | null;
  provider: ProviderReadiness; worker: string; worker_heartbeat_at: string | null; recent: VoiceCall[];
}
export interface VoiceSettings {
  version: number; mode: "disabled" | "mock"; ring_seconds: number; transfer_seconds: number;
  max_duration_seconds: number; max_concurrent_calls: number; daily_call_limit: number;
  monthly_minute_limit: number; calls_per_minute: number; retry_limit: number;
  retry_interval_seconds: number; queue_timeout_seconds: number; max_queue_length: number;
  ai_fallback: boolean; timezone: string; calling_start: string; calling_end: string;
  holidays: string[]; primary_employee_id: string | null; conversation_instructions: string;
  operational_rules: string; default_language: string;
}
export interface Article {
  id: string; version: number; title: string; content: string; language: string; status: string;
  effective_on: string | null; expires_on: string | null; revisions: { version: number }[];
}
export interface ConsoleResult {
  response: string | null; mode: string; language: string; uncertain: boolean; escalate?: boolean;
  warnings: string[]; sources: { id: string; title: string; version: number; excerpt: string }[];
}
const base = "/voice-assistant";
export const getDashboard = () => apiRequest<VoiceDashboard>(`${base}/dashboard`);
export const getSettings = () => apiRequest<VoiceSettings>(`${base}/settings`);
export const saveSettings = (data: VoiceSettings) => apiRequest<VoiceSettings>(`${base}/settings`, { method: "PUT", body: JSON.stringify(data) });
export const getCalls = (page: number, status: string, direction: string) => apiRequest<{ items: VoiceCall[]; total: number; total_pages: number }>(`${base}/calls?${new URLSearchParams({ page: String(page), ...(status ? { status } : {}), ...(direction ? { direction } : {}) })}`);
export const getCall = (id: string) => apiRequest<VoiceCall>(`${base}/calls/${id}`);
export const simulateCall = (direction: string, contact_label: string, consent_reference: string, idempotency_key: string) => apiRequest<VoiceCall>(`${base}/mock/calls`, { method: "POST", body: JSON.stringify({ direction, contact_label, idempotency_key, ...(consent_reference ? { consent_reference } : {}) }) });
export const callAction = (call: VoiceCall, action: string) => apiRequest<VoiceCall>(`${base}/mock/calls/${call.id}/actions`, { method: "POST", body: JSON.stringify({ action, version: call.version }) });
export const getKnowledge = (page: number) => apiRequest<{ items: Article[]; total: number }>(`${base}/knowledge?page=${page}`);
export const saveArticle = (data: Omit<Article, "id" | "status" | "revisions">, id?: string) => apiRequest<Article>(`${base}/knowledge${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
export const articleAction = (article: Article, action: string, target_version?: number) => apiRequest<Article>(`${base}/knowledge/${article.id}/actions`, { method: "POST", body: JSON.stringify({ action, version: article.version, ...(target_version ? { target_version } : {}) }) });
export const testConversation = (question: string, language: string, history: { role: string; content: string }[]) => apiRequest<ConsoleResult>(`${base}/console`, { method: "POST", body: JSON.stringify({ question, language, history }) });
