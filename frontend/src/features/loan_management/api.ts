import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";
import { getCurrentCoordinates } from "@/shared/geolocation";

export interface LoanCaseDetails {
  credit_score: number | null;
  credit_remarks: string | null;
  bank_nbfc_name: string | null;
  bank_application_id: string | null;
  bank_reference_number: string | null;
  assigned_officer: string | null;
  bank_decision: string | null;
  bank_remarks: string | null;
  offered_amount: number | null;
  offered_tenure_months: number | null;
  offered_interest_rate: number | null;
  offer_decision: string;
  esign_completed: boolean;
  nach_completed: boolean;
  kyc_completed: boolean;
  final_evaluation_remarks: string | null;
  disbursed_amount: number | null;
  disbursed_at: string | null;
  disbursed_reference: string | null;
}

export interface LoanCaseListItem {
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

export interface LoanCaseDetail extends LoanCaseListItem {
  pending_document_type_ids: string[];
  loan_details: LoanCaseDetails;
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

export async function listLoanCases(params: {
  page?: number; page_size?: number; search?: string; status?: string; assigned_to?: string; unassigned_only?: boolean;
}): Promise<PaginatedResponse<LoanCaseListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<LoanCaseListItem[]>(`/loan-cases${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getLoanCase(caseId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}`);
}

export function getLoanCaseTimeline(caseId: string) {
  return apiRequest<CaseTimelineEntry[]>(`/loan-cases/${caseId}/timeline`);
}

export function addLoanCaseNote(caseId: string, text: string) {
  return apiRequest<{ id: string }>(`/loan-cases/${caseId}/notes`, { method: "POST", body: JSON.stringify({ text }) });
}

export function assignLoanCase(caseId: string, employeeId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/assign`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) });
}

// Generic Case Status control (Loan Case detail page) — the same source of truth as
// every other write here: the backend re-validates the status value against
// `LoanStatus.ALL` and the existing Workflow Engine transition graph, so this can never
// persist an Insurance status or an out-of-order jump even if called directly.
export function updateLoanCaseStatus(caseId: string, status: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
}

export function holdLoanCase(caseId: string, reason: string, remarks?: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/hold`, { method: "POST", body: JSON.stringify({ reason, remarks }) });
}

export function resumeLoanCase(caseId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/resume`, { method: "POST" });
}

export function requestLoanCaseDocuments(caseId: string, documentTypeIds: string[]) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/documents/request`, { method: "POST", body: JSON.stringify({ document_type_ids: documentTypeIds }) });
}

export async function verifyLoanCaseDocuments(caseId: string) {
  // Best-effort — only checked server-side if a Geo Fence is configured for
  // document_collection; see @/shared/geolocation.
  const coords = await getCurrentCoordinates();
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/documents/verify`, {
    method: "POST",
    body: JSON.stringify({ latitude: coords?.latitude, longitude: coords?.longitude }),
  });
}

export function recordBankDetails(
  caseId: string,
  payload: { bank_nbfc_name?: string; bank_application_id?: string; bank_reference_number?: string; assigned_officer?: string; bank_decision?: string; bank_remarks?: string }
) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/bank-details`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordCreditEvaluation(
  caseId: string,
  payload: { credit_score?: number; credit_remarks?: string; decision: "approved" | "rejected"; rejection_reason?: string }
) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/credit-evaluation`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordOffer(caseId: string, payload: { offered_amount: number; offered_tenure_months: number; offered_interest_rate: number }) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/offer`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordEsignNachKyc(caseId: string, payload: { esign_completed: boolean; nach_completed: boolean; kyc_completed: boolean }) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/esign-nach-kyc`, { method: "POST", body: JSON.stringify(payload) });
}

export function recordFinalEvaluation(caseId: string, payload: { remarks?: string; decision: "approved" | "rejected"; rejection_reason?: string }) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/final-evaluation`, { method: "POST", body: JSON.stringify(payload) });
}

export function disburseLoanCase(caseId: string, payload: { disbursed_amount: number; disbursed_reference: string }) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/disburse`, { method: "POST", body: JSON.stringify(payload) });
}
