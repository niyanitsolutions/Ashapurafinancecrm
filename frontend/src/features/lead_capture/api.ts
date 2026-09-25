import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface CaptureSource {
  id: string;
  key: string;
  label: string;
  lead_source_id: string;
  default_product_category: string | null;
  default_product_id: string | null;
}

export interface CaptureFailure {
  id: string;
  capture_source: string;
  failure_reason: string;
  raw_payload: Record<string, unknown>;
  error_detail: string | null;
  status: string;
  retry_count: number;
  next_retry_at: string | null;
  resolved_lead_id: string | null;
  created_at: string;
}

export interface MetaLeadRouting {
  id: string;
  meta_form_id: string;
  form_name: string;
  category: "loan" | "insurance" | null;
  product_mode: "default" | "customer_answer" | null;
  default_product_id: string | null;
  destination_module: "leads" | "insurance_policy_leads" | null;
  destination_type: string | null;
  product_question_key: string | null;
  product_question_label: string | null;
  answer_mappings: Record<string, string>;
  discovered_questions: string[];
  priority: number;
  status: "active" | "inactive" | "unconfigured";
  created_at: string;
  updated_at: string;
}

export interface MetaLeadRoutingInput {
  form_name?: string;
  category: "loan" | "insurance";
  product_mode: "default" | "customer_answer";
  default_product_id?: string | null;
  destination_module: "leads" | "insurance_policy_leads";
  destination_type?: string | null;
  product_question_key?: string | null;
  product_question_label?: string | null;
  answer_mappings: Record<string, string>;
  active: boolean;
  priority?: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

export function listCaptureSources() {
  return apiRequest<CaptureSource[]>("/lead-capture/sources");
}

export function updateCaptureSource(key: string, payload: { lead_source_id?: string; default_product_category?: string; default_product_id?: string }) {
  return apiRequest<CaptureSource>(`/lead-capture/sources/${key}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function captureManualLead(payload: { full_name: string; mobile: string; email?: string; product_category: string; product_id: string; remarks?: string }) {
  return apiRequest<{ lead_code: string; lead_id: string }>("/lead-capture/manual", { method: "POST", body: JSON.stringify(payload) });
}

export async function listCaptureFailures(params: { page?: number; page_size?: number; capture_source?: string; status?: string }): Promise<PaginatedResponse<CaptureFailure>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<CaptureFailure[]>(`/lead-capture/failures${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function retryCaptureFailure(failureId: string) {
  return apiRequest<CaptureFailure>(`/lead-capture/failures/${failureId}/retry`, { method: "POST" });
}

export function listMetaLeadRoutings() {
  return apiRequest<MetaLeadRouting[]>("/lead-capture/meta-routings");
}

export function syncMetaLeadRoutings() {
  return apiRequest<MetaLeadRouting[]>("/lead-capture/meta-routings/sync", { method: "POST" });
}

export function saveMetaLeadRouting(formId: string, payload: MetaLeadRoutingInput) {
  return apiRequest<MetaLeadRouting>(`/lead-capture/meta-routings/${encodeURIComponent(formId)}`, {
    method: "PUT", body: JSON.stringify(payload),
  });
}

export function setMetaLeadRoutingStatus(formId: string, active: boolean) {
  return apiRequest<MetaLeadRouting>(`/lead-capture/meta-routings/${encodeURIComponent(formId)}/status`, {
    method: "PATCH", body: JSON.stringify({ active }),
  });
}
