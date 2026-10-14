import { apiBlob, apiRequest } from "@/shared/api/client";

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
  operational?: Record<string, string | number | null | Record<string, number>>;
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
  source?: { kind: string; format: string; scan_status: string; size_bytes: number } | null;
  publication?: { version: number; title: string; published_at: string; published_by: string } | null;
  publications?: { version: number; title: string; published_at: string }[];
}
export interface ConsoleResult {
  response: string | null; mode: string; language: string; uncertain: boolean; escalate?: boolean;
  warnings: string[]; sources: { id: string; title: string; version: number; excerpt: string }[];
}
const base = "/voice-assistant";
export interface Campaign { id: string; version: number; name: string; purpose: string; objective: string; timezone: string; status: string; mode: string; processing_counts: Record<string, number> }
export interface CampaignPreview { items: { customer_id: string; eligible: boolean; reason: string }[]; calls_placed: number; production_dispatch: string }
export const getCampaigns = (page: number) => apiRequest<{ items: Campaign[]; total: number }>(`${base}/campaigns?page=${page}`);
export const createCampaign = (name: string, purpose: string, objective: string, timezone: string) => apiRequest<Campaign>(`${base}/campaigns`, { method: "POST", body: JSON.stringify({ name, purpose, objective, timezone, mode: "dry_run" }) });
export const campaignAction = (campaign: Campaign, action: string) => apiRequest<Campaign>(`${base}/campaigns/${campaign.id}/actions`, { method: "POST", body: JSON.stringify({ version: campaign.version, action }) });
export const importCampaignAudience = (id: string, data: FormData) => apiRequest(`${base}/campaigns/${id}/recipients/import`, { method: "POST", body: data });
export const previewCampaign = (id: string) => apiRequest<CampaignPreview>(`${base}/campaigns/${id}/preview`, { method: "POST" });
export const stopCampaigns = (reason: string) => apiRequest(`${base}/campaign-controls/emergency`, { method: "POST", body: JSON.stringify({ stopped: true, reason }) });
export interface ContactPolicy { id: string; version: number; purpose?: string; scope?: string; action?: string; suppressed?: boolean; expires_at?: string; verification?: string }
export const getContactPolicies = (customerId: string) => apiRequest<{ consents: ContactPolicy[]; suppressions: ContactPolicy[] }>(`${base}/contact-policies/${customerId}`);
export const saveContactConsent = (data: { customer_id: string; version: number; purpose: string; action: "grant" | "withdraw"; evidence_reference: string; expires_at: string | null }) => apiRequest<ContactPolicy>(`${base}/contact-policies/consent`, { method: "PUT", body: JSON.stringify(data) });
export const saveContactSuppression = (data: { customer_id: string; version: number; suppressed: boolean; reason: string }) => apiRequest<ContactPolicy>(`${base}/contact-policies/suppression`, { method: "PUT", body: JSON.stringify(data) });
export const getDashboard = () => apiRequest<VoiceDashboard>(`${base}/dashboard`);
export const getSettings = () => apiRequest<VoiceSettings>(`${base}/settings`);
export const saveSettings = (data: VoiceSettings) => apiRequest<VoiceSettings>(`${base}/settings`, { method: "PUT", body: JSON.stringify(data) });
export const getCalls = (page: number, status: string, direction: string) => apiRequest<{ items: VoiceCall[]; total: number; total_pages: number }>(`${base}/calls?${new URLSearchParams({ page: String(page), ...(status ? { status } : {}), ...(direction ? { direction } : {}) })}`);
export const getCall = (id: string) => apiRequest<VoiceCall>(`${base}/calls/${id}`);
export const simulateCall = (direction: string, contact_label: string, consent_reference: string, idempotency_key: string) => apiRequest<VoiceCall>(`${base}/mock/calls`, { method: "POST", body: JSON.stringify({ direction, contact_label, idempotency_key, ...(consent_reference ? { consent_reference } : {}) }) });
export const callAction = (call: VoiceCall, action: string) => apiRequest<VoiceCall>(`${base}/mock/calls/${call.id}/actions`, { method: "POST", body: JSON.stringify({ action, version: call.version }) });
export const getKnowledge = (page: number) => apiRequest<{ items: Article[]; total: number }>(`${base}/knowledge?page=${page}`);
export const saveArticle = (data: Pick<Article, "title" | "content" | "language" | "effective_on" | "expires_on" | "version">, id?: string) => apiRequest<Article>(`${base}/knowledge${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
export const articleAction = (article: Article, action: string, target_version?: number) => apiRequest<Article>(`${base}/knowledge/${article.id}/actions`, { method: "POST", body: JSON.stringify({ action, version: article.version, ...(target_version ? { target_version } : {}) }) });
export const testConversation = (question: string, language: string, history: { role: string; content: string }[]) => apiRequest<ConsoleResult>(`${base}/console`, { method: "POST", body: JSON.stringify({ question, language, history }) });

export interface EvaluationCase { question: string; required_facts: string[]; expect_evidence: boolean }
export interface KnowledgeEvaluation {
  id: string; evaluated_version: number; passed: boolean; kind: string; latency_ms: number;
  semantic_groundedness: string; prompt_injection_resistance: string;
  cases: (EvaluationCase & { passed: boolean; missing_facts: string[]; excerpts: string[] })[];
}
export const importKnowledge = (data: FormData) => apiRequest<Article>(`${base}/knowledge/import`, { method: "POST", body: data });
export const evaluateKnowledge = (article: Article, cases: EvaluationCase[]) => apiRequest<KnowledgeEvaluation>(`${base}/knowledge/${article.id}/evaluations`, { method: "POST", body: JSON.stringify({ version: article.version, cases }) });
export const getEvaluations = (id: string) => apiRequest<KnowledgeEvaluation[]>(`${base}/knowledge/${id}/evaluations`);

export interface Recording {
  id: string; version: number; call_id: string; direction: string; status: string; origin: string;
  call_provider: string; duration_seconds: number; size_bytes: number; sample_rate: number; channels: number;
  created_at: string; expires_at: string; transcript_status: string;
  language?: string; call_outcome?: string;
}
export interface RecordingList { items: Recording[]; total: number; page: number; storage: string; live_capture: string; transcription_engine: string }
export interface TranscriptSegment { speaker: string; start_seconds: number; end_seconds: number; text: string; confidence?: number | null }
export interface Transcript { language: string; recognizer_label: string; segments: TranscriptSegment[]; provenance: string; summary: null; summary_status: string }
export const getRecordings = (page: number, status: string, callId: string, since = "", until = "") => apiRequest<RecordingList>(`${base}/recordings?${new URLSearchParams({ page: String(page), ...(status ? { status } : {}), ...(callId ? { call_id: callId } : {}), ...(since ? { since } : {}), ...(until ? { until } : {}) })}`);
export const importRecording = (data: FormData) => apiRequest<Recording>(`${base}/recordings/import`, { method: "POST", body: data });
export const getRecordingAudio = (id: string, download = false) => apiBlob(`${base}/recordings/${id}/audio?download=${download}`);
export const getTranscript = (id: string) => apiRequest<Transcript>(`${base}/recordings/${id}/transcript`);
export const saveTranscript = (record: Recording, data: Pick<Transcript, "language" | "recognizer_label" | "segments">) => apiRequest<{ version: number; status: string }>(`${base}/recordings/${record.id}/transcript`, { method: "PUT", body: JSON.stringify({ ...data, version: record.version }) });
export const deleteRecording = (record: Recording) => apiRequest<{ status: string }>(`${base}/recordings/${record.id}?version=${record.version}`, { method: "DELETE" });
export const recoverRecording = (record: Recording) => apiRequest<Recording>(`${base}/recordings/${record.id}/recover?version=${record.version}`, { method: "POST" });

export interface SmartfloConnection {
  version: number; api_base_url: string; public_origin: string | null;
  api_token_configured: boolean; callback_token_configured: boolean; token_expires_at: string | null;
  token_expired: boolean; callback_mode: "disabled" | "validation_only"; connection_status: string;
  last_test: { message: string; tested_at: string } | null;
  sandbox: string; audio_status: string; url_verification: string;
  incoming_webhook_url: string | null; answered_webhook_url: string | null;
  call_status_webhook_url: string | null; dynamic_endpoint_url: string | null;
  audio_websocket_url: string | null; warnings: string[];
}
export interface SmartfloEvent { trigger: string; provider_call_id: string; received_at: string; status: string }
const smartflo = `${base}/smartflo`;
export const getSmartfloConnection = () => apiRequest<SmartfloConnection>(`${smartflo}/connection`);
export const saveSmartfloConnection = (payload: {
  version: number; api_base_url: string; public_origin: string | null;
  api_token?: string; callback_token?: string; clear_api_token: boolean; clear_callback_token: boolean;
  callback_mode: "disabled" | "validation_only"; token_expires_at: string | null;
}) => apiRequest<SmartfloConnection>(`${smartflo}/connection`, { method: "PUT", body: JSON.stringify(payload) });
export const testSmartflo = (kind: "connection" | "webhook" | "audio") => apiRequest<{ status: string; message: string }>(`${smartflo}/tests/${kind}`, { method: "POST" });
export const getSmartfloEvents = (page: number) => apiRequest<{ items: SmartfloEvent[]; total: number }>(`${smartflo}/events?page=${page}`);
