import { apiRequest } from "@/shared/api/client";

export interface IntegrationProvider {
  id: string;
  integration_type: string;
  provider: string;
  label: string;
}

export interface IntegrationConfig {
  id: string;
  integration_code: string;
  integration_type: string;
  provider: string;
  name: string;
  config: Record<string, string>;
  is_enabled: boolean;
  is_active: boolean;
  last_tested_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_message: string | null;
  activated_at: string | null;
  webhook_verified_at: string | null;
  health_status: "healthy" | "warning" | "error" | null;
  created_at: string;
  updated_at: string;
  // Only set on the response to createIntegrationConfig for a freshly-created Meta
  // config with auto-generated webhook credentials — see IntegrationListPage's reveal
  // panel. `null` on every other read; `config.webhook_verify_token`/`webhook_secret`
  // are masked again from then on, same as any other secret field.
  webhook_callback_path: string | null;
}

export interface ConnectionCheckItem {
  key: string;
  label: string;
  passed: boolean;
  detail: string | null;
}

export interface TestConnectionResult {
  success: boolean;
  response_time_ms: number;
  error_message: string | null;
  tested_at: string;
  checks: ConnectionCheckItem[] | null;
}

export interface IntegrationTestLog {
  id: string;
  success: boolean;
  response_time_ms: number;
  error_message: string | null;
  tested_at: string;
  graph_api_version: string | null;
  tested_ip: string | null;
}

export interface SetupProgress {
  credentials_entered: boolean;
  test_connection_passed: boolean;
  saved: boolean;
  activated: boolean;
  webhook_verified: boolean;
  first_lead_received: boolean;
}

export interface MissingPermission {
  permission: string;
  why_needed: string;
}

export interface MetaStatus {
  health_status: "healthy" | "warning" | "error" | null;
  setup_progress: SetupProgress;
  completed_steps: number;
  total_steps: number;
  ad_accounts_count: number | null;
  pages_count: number | null;
  lead_forms_count: number | null;
  webhook_verified_at: string | null;
  last_lead_received_at: string | null;
  total_leads_imported: number;
  connected_since: string | null;
  missing_permissions: MissingPermission[];
  token_expires_at: string | null;
  belongs_to_app_name: string | null;
  graph_api_version: string;
  user_token_expires_at: string | null;
  last_token_refresh_at: string | null;
  connected_page_name: string | null;
  connected_ad_account_id: string | null;
  connected_form_count: number | null;
}

export function listIntegrationProviders() {
  return apiRequest<IntegrationProvider[]>("/integration-providers");
}

export function createIntegrationConfig(payload: { integration_type: string; provider: string; name: string; config: Record<string, string> }) {
  return apiRequest<IntegrationConfig>("/integration-configs", { method: "POST", body: JSON.stringify(payload) });
}

export function listIntegrationConfigs(integrationType?: string) {
  const qs = integrationType ? `?integration_type=${integrationType}` : "";
  return apiRequest<IntegrationConfig[]>(`/integration-configs${qs}`);
}

export function getIntegrationConfig(configId: string) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}`);
}

export function updateIntegrationConfig(configId: string, payload: { name?: string; config?: Record<string, string> }) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function enableIntegrationConfig(configId: string) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}/enable`, { method: "PATCH" });
}

export function disableIntegrationConfig(configId: string) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}/disable`, { method: "PATCH" });
}

export function activateIntegrationConfig(configId: string) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}/activate`, { method: "POST" });
}

export function testIntegrationConnection(configId: string) {
  return apiRequest<TestConnectionResult>(`/integration-configs/${configId}/test`, { method: "POST" });
}

export function listIntegrationTestLogs(configId: string) {
  return apiRequest<IntegrationTestLog[]>(`/integration-configs/${configId}/test-logs`);
}

// Tests raw credentials before any config row exists — nothing is persisted server-side.
// `provider` is optional (defaults server-side to ""); pass it whenever a provider-specific
// tester branch exists (e.g. MSG91's real balance/auth checks vs. the generic SMS/WhatsApp
// field-presence check) — see testers.py.
export function testDraftConnection(payload: { integration_type: string; provider?: string; config: Record<string, string> }) {
  return apiRequest<TestConnectionResult>("/integration-configs/test-draft", { method: "POST", body: JSON.stringify(payload) });
}

export function getMetaStatus(configId: string) {
  return apiRequest<MetaStatus>(`/integration-configs/${configId}/meta-status`);
}

// ---------------------------------------------------------------------- Meta OAuth Connect flow

export interface OAuthOption {
  id: string;
  name: string;
}

export interface OAuthPageOption extends OAuthOption {
  // Non-empty only when the Page has a linked Instagram Business Account — Instagram
  // Lead Ads share this Page's leadgen webhook subscription, so there's no separate
  // Instagram picker step, just this visibility into which Page also covers it.
  instagram_username: string;
}

export interface OAuthSession {
  pages: OAuthPageOption[];
  ad_accounts: OAuthOption[];
}

export function startMetaOAuth(configId: string) {
  return apiRequest<{ authorize_url: string }>(`/integration-configs/${configId}/oauth/login`);
}

export function getOAuthSession(configId: string, sessionId: string) {
  return apiRequest<OAuthSession>(`/integration-configs/${configId}/oauth/session/${sessionId}`);
}

export function listOAuthForms(configId: string, sessionId: string, pageId: string) {
  return apiRequest<OAuthOption[]>(`/integration-configs/${configId}/oauth/session/${sessionId}/forms?page_id=${encodeURIComponent(pageId)}`);
}

export function connectMetaOAuth(configId: string, sessionId: string, payload: { page_id: string; ad_account_id: string | null; selected_forms: string[] }) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}/oauth/session/${sessionId}/connect`, { method: "POST", body: JSON.stringify(payload) });
}

export function disconnectMeta(configId: string) {
  return apiRequest<IntegrationConfig>(`/integration-configs/${configId}/oauth/disconnect`, { method: "POST" });
}

// "Sync Forms" on the Status panel — re-fetches the connected Page's current Lead Forms
// using the already-stored token, distinct from the one-time picker session above.
export function syncMetaForms(configId: string) {
  return apiRequest<OAuthOption[]>(`/integration-configs/${configId}/oauth/forms`);
}
