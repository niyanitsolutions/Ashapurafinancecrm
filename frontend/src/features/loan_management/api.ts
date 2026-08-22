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
  rv_ov_ref_type: string | null;
  rv_ov_ref_status: string | null;
  rv_ov_ref_date: string | null;
  rv_ov_ref_verified_by: string | null;
  rv_ov_ref_result: string | null;
  rv_ov_ref_remarks: string | null;
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
  // Decision #130 — the backend's own, real, configured next-status options for
  // `current_status` (`WorkflowDefinition.allowed_next_statuses`), so the Update modal's
  // dropdown reflects the actual transition graph rather than only `statusControl.ts`'s
  // hand-maintained hint.
  allowed_next_statuses: string[];
  selected_bank_name: string | null;
  approved_amount: number | null;
  created_at: string;
}

// One bank/NBFC offer on a Loan Case's Credit Evaluation (decision #129) — a case can
// carry any number of these; adding one never overwrites another.
export interface BankOffer {
  id: string;
  loan_case_id: string;
  bank_name: string;
  bank_application_id: string | null;
  reference_number: string | null;
  assigned_officer: string | null;
  decision: "approved" | "rejected_re_eligible";
  approved_amount: number | null;
  remarks: string | null;
  is_selected: boolean;
  selected_at: string | null;
  selected_by: string | null;
  created_at: string;
  updated_at: string;
}

// Customer-facing view — approved offers only, trimmed to exactly bank name + amount
// (no bank_application_id/assigned_officer/reference_number/remarks/decision).
export interface CustomerBankOffer {
  id: string;
  bank_name: string;
  approved_amount: number;
}

export interface LoanCaseCounts {
  new_customer: number;
  credit_evaluation: number;
  offer_acceptance: number;
  additional_documents: number;
  rv_ov_ref: number;
  esign_nach_kyc: number;
  final_evaluation: number;
  send_for_disbursement: number;
  disbursed: number;
  on_hold: number;
  re_eligible: number;
  rejected: number;
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

// Customer self-service ("mine") list/detail — used by the Portal to resolve which
// Loan Case belongs to the customer's own application before showing bank offers.
export function listOwnLoanCases() {
  return apiRequest<LoanCaseListItem[]>("/loan-cases/mine");
}

export function getOwnLoanCase(caseId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/mine/${caseId}`);
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
export function updateLoanCaseStatus(caseId: string, status: string, remarks?: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/status`, { method: "PATCH", body: JSON.stringify({ status, remarks }) });
}

export function getLoanCaseCounts() {
  return apiRequest<LoanCaseCounts>("/loan-cases/counts");
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

// Case-level credit score/remarks only (decision #129) — pure data capture, independent
// of any individual bank's own decision (see the bank-offer functions below) and never
// itself moves the case out of Credit Evaluation.
export function recordCreditEvaluation(caseId: string, payload: { credit_score?: number; credit_remarks?: string }) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/credit-evaluation`, { method: "POST", body: JSON.stringify(payload) });
}

export interface BankOfferPayload {
  bank_name: string;
  bank_application_id?: string;
  reference_number?: string;
  assigned_officer?: string;
  decision: "approved" | "rejected_re_eligible";
  approved_amount?: number;
  remarks?: string;
}

export function listBankOffers(caseId: string) {
  return apiRequest<BankOffer[]>(`/loan-cases/${caseId}/bank-offers`);
}

export function addBankOffer(caseId: string, payload: BankOfferPayload) {
  return apiRequest<BankOffer>(`/loan-cases/${caseId}/bank-offers`, { method: "POST", body: JSON.stringify(payload) });
}

export function updateBankOffer(caseId: string, offerId: string, payload: BankOfferPayload) {
  return apiRequest<BankOffer>(`/loan-cases/${caseId}/bank-offers/${offerId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

// Selection only — marks which offer the case proceeds with and moves it to Offer
// Acceptance. Deliberately does NOT itself confirm acceptance; see confirmOfferAcceptance.
export function selectBankOffer(caseId: string, offerId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/bank-offers/${offerId}/select`, { method: "POST" });
}

export function confirmOfferAcceptance(caseId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/offer-acceptance/confirm`, { method: "POST" });
}

// Customer self-service ("mine") — approved offers only, trimmed fields.
export function listOwnBankOffers(caseId: string) {
  return apiRequest<CustomerBankOffer[]>(`/loan-cases/mine/${caseId}/bank-offers`);
}

export function selectOwnBankOffer(caseId: string, offerId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/mine/${caseId}/bank-offers/${offerId}/select`, { method: "POST" });
}

export function confirmOwnOfferAcceptance(caseId: string) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/mine/${caseId}/offer-acceptance/confirm`, { method: "POST" });
}

// RV/OV/Ref stage data (decision #130) — valid only while the case is at `rv_ov_ref`;
// recording it advances the case to `esign_nach_kyc`.
export interface RvOvRefPayload {
  rv_ov_ref_type: string;
  rv_ov_ref_status: string;
  rv_ov_ref_date: string;
  rv_ov_ref_verified_by: string;
  rv_ov_ref_result: string;
  rv_ov_ref_remarks?: string;
}

export function recordRvOvRef(caseId: string, payload: RvOvRefPayload) {
  return apiRequest<LoanCaseDetail>(`/loan-cases/${caseId}/rv-ov-ref`, { method: "POST", body: JSON.stringify(payload) });
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
