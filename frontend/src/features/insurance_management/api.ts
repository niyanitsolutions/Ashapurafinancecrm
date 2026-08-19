import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";
import { getCurrentCoordinates } from "@/shared/geolocation";

export interface InsuranceCaseDetails {
  sum_insured: number | null;
  underwriting_remarks: string | null;
  requires_medical: boolean;
  requires_additional_documents: boolean;
  medical_verification_outcome: string | null;
  medical_verification_remarks: string | null;
  premium_amount: number | null;
  premium_decision: string;
  policy_number: string | null;
  policy_generated_at: string | null;
  policy_issued_at: string | null;
}

export interface InsuranceCaseListItem {
  id: string;
  case_code: string;
  application_id: string;
  customer_id: string;
  customer_name: string | null;
  product_id: string;
  product_name: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  current_status: string;
  rejection_reason: string | null;
  created_at: string;
}

export interface InsuranceCaseDetail extends InsuranceCaseListItem {
  pending_document_type_ids: string[];
  insurance_details: InsuranceCaseDetails;
  updated_at: string;
}

export interface CaseTimelineEntry {
  type: string;
  from_status: string | null;
  to_status: string | null;
  remarks: string | null;
  text: string | null;
  created_by: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

export async function listInsuranceCases(params: {
  page?: number; page_size?: number; search?: string; status?: string; assigned_to?: string; unassigned_only?: boolean;
}): Promise<PaginatedResponse<InsuranceCaseListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<InsuranceCaseListItem[]>(`/insurance-cases${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getInsuranceCase(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}`);
}

export function getInsuranceCaseTimeline(caseId: string) {
  return apiRequest<CaseTimelineEntry[]>(`/insurance-cases/${caseId}/timeline`);
}

export function addInsuranceCaseNote(caseId: string, text: string) {
  return apiRequest<{ id: string }>(`/insurance-cases/${caseId}/notes`, { method: "POST", body: JSON.stringify({ text }) });
}

export function assignInsuranceCase(caseId: string, employeeId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/assign`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) });
}

// Generic Case Status control (Insurance Case detail page) — mirrors
// `loan_management/api.ts`'s `updateLoanCaseStatus`; the backend validates against
// `InsuranceStatus.ALL` and its own transition graph, never `LoanStatus`.
export function updateInsuranceCaseStatus(caseId: string, status: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function holdInsuranceCase(caseId: string, reason: string, remarks?: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/hold`, { method: "POST", body: JSON.stringify({ reason, remarks }) });
}

export function resumeInsuranceCase(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/resume`, { method: "POST" });
}

export function requestInsuranceCaseDocuments(caseId: string, documentTypeIds: string[]) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/documents/request`, { method: "POST", body: JSON.stringify({ document_type_ids: documentTypeIds }) });
}

export async function verifyInsuranceCaseDocuments(caseId: string) {
  // Best-effort — only checked server-side if a Geo Fence is configured for
  // document_collection; see @/shared/geolocation.
  const coords = await getCurrentCoordinates();
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/documents/verify`, {
    method: "POST",
    body: JSON.stringify({ latitude: coords?.latitude, longitude: coords?.longitude }),
  });
}

export function recordUnderwriting(
  caseId: string,
  payload: {
    sum_insured?: number; underwriting_remarks?: string; requires_medical: boolean; requires_additional_documents: boolean;
    decision: "approved" | "rejected"; rejection_reason?: string;
  }
) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/underwriting`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordMedicalVerification(caseId: string, payload: { outcome: "cleared" | "failed"; medical_remarks?: string; rejection_reason?: string }) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/medical-verification`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordPremium(caseId: string, payload: { premium_amount: number }) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/premium`, { method: "POST", body: JSON.stringify(payload) });
}

export function generatePolicy(caseId: string, payload: { policy_number: string }) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/policy/generate`, { method: "POST", body: JSON.stringify(payload) });
}

export function issuePolicy(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/policy/issue`, { method: "POST" });
}
