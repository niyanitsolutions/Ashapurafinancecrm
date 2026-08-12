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
