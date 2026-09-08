import { ApiError, apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";
import type { ApplicationDocument } from "@/features/customer/api";
import { getCurrentCoordinates } from "@/shared/geolocation";

// Insurance "Policy Leads" pipeline (redesign 2026-09) — the full replacement of the
// old 6C underwriting/medical/premium flow. New statuses:
//   fresh_lead -> policy_document -> policy_login -> policy_issued
// plus re_eligible / rejected / on_hold. Premium / PPT / PT are recorded by staff at
// Policy Login. Every transition is backend-validated (WorkflowEngine + service gates);
// nothing here is an enforcement authority.

export type InsuranceStatus =
  | "fresh_lead"
  | "policy_document"
  | "policy_login"
  | "policy_issued"
  | "re_eligible"
  | "on_hold"
  | "rejected";

export interface InsuranceCaseDetails {
  sum_insured: number | null;
  premium_amount: number | null;
  ppt: number | null;
  pt: number | null;
  policy_login_remarks: string | null;
  policy_number: string | null;
  policy_issued_at: string | null;
  re_eligibility_choice: string | null;
  re_eligible_date: string | null;
  re_eligibility_auto_transitioned: boolean;
}

export interface RequiredDocumentsSummary {
  required_total: number;
  verified_total: number;
  all_required_verified: boolean;
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
  next_follow_up_date: string | null;
  created_at: string;
}

export interface InsuranceCaseDetail extends InsuranceCaseListItem {
  insurance_details: InsuranceCaseDetails;
  required_documents: RequiredDocumentsSummary;
  updated_at: string;
}

// The schema documents on a case's application — `is_in_schema` is false for a document
// left behind by a `change_product` (shown under "Previously uploaded").
export interface InsuranceCaseDocument extends ApplicationDocument {
  is_in_schema: boolean;
}

export interface OtherDocument {
  id: string;
  insurance_case_id: string;
  name: string;
  document_status: "requested" | "uploaded";
  verification_status: "pending" | "verified" | "rejected";
  rejection_reason: string | null;
  file_name: string | null;
  download_url: string | null;
  attachment_url: string | null;
  uploaded_at: string | null;
  verified_at: string | null;
  created_at: string;
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

export function holdInsuranceCase(caseId: string, reason: string, remarks?: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/hold`, { method: "POST", body: JSON.stringify({ reason, remarks }) });
}

export function resumeInsuranceCase(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/resume`, { method: "POST" });
}

// ---------------------------------------------------------------- pipeline transitions

export function moveToPolicyDocument(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/move-to-policy-document`, { method: "POST" });
}

export async function moveToPolicyLogin(caseId: string) {
  // Best-effort coordinates — only checked server-side when a Geo Fence is configured
  // for document_collection (same as loan's document verification).
  const coords = await getCurrentCoordinates();
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/move-to-policy-login`, {
    method: "POST",
    body: JSON.stringify({ latitude: coords?.latitude, longitude: coords?.longitude }),
  });
}

export function moveToPolicyIssued(caseId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/move-to-policy-issued`, { method: "POST" });
}

// "Move Back" one stage — the backend derives the single valid target from the
// transition graph (`policy_login -> policy_document`, `policy_document -> fresh_lead`).
export function moveInsuranceCaseBack(caseId: string, target: "fresh_lead" | "policy_document") {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/move-back`, { method: "POST", body: JSON.stringify({ target }) });
}

export function restartFromReEligible(caseId: string, target: "fresh_lead" | "policy_document") {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/restart`, { method: "POST", body: JSON.stringify({ target }) });
}

// Reject popup — insurance offers 3 / 6 / 12 / Custom / No (no 9-month option). "no"
// means "never automatically Re-Eligible". `re_eligible_date` (yyyy-mm-dd) only with "custom".
export type InsuranceReEligibilityChoice = "3_months" | "6_months" | "12_months" | "custom" | "no";

export function rejectInsuranceCase(
  caseId: string,
  payload: { reason: string; re_eligibility: InsuranceReEligibilityChoice; re_eligible_date?: string },
) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/reject`, { method: "POST", body: JSON.stringify(payload) });
}

// Policy Login "Update" — Premium / PPT / PT / Remarks / Policy Number, and optionally a
// product change in the same call (the backend runs `change_product` when `product_id`
// differs).
export function updatePolicyLogin(
  caseId: string,
  payload: { product_id?: string; premium_amount?: number; ppt?: number; pt?: number; remarks?: string; policy_number?: string },
) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/policy-login`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function changeInsuranceProduct(caseId: string, productId: string) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/change-product`, { method: "POST", body: JSON.stringify({ product_id: productId }) });
}

// ---------------------------------------------------------------- manual lead creation + staff "Move To"

// Stages a manual lead can be created in directly. Policy Login / Policy Issued need
// documents / premium that only exist after the lead does — reach them via "Move To".
export const MANUAL_CREATE_STAGES: { value: string; label: string }[] = [
  { value: "fresh_lead", label: "Fresh Lead" },
  { value: "policy_document", label: "Policy Document" },
  { value: "re_eligible", label: "Re-Eligible" },
  { value: "rejected", label: "Rejected" },
];

export interface CreateManualInsuranceCasePayload {
  full_name: string;
  mobile: string;
  email?: string;
  gender?: string;
  age?: number;
  profession?: string;
  annual_income?: number;
  remarks?: string;
  insurance_category_id: string;
  product_id: string;
  stage: string;
  reason?: string;
  re_eligibility?: InsuranceReEligibilityChoice;
  re_eligible_date?: string;
}

export function createManualInsuranceCase(payload: CreateManualInsuranceCasePayload) {
  return apiRequest<InsuranceCaseDetail>("/insurance-cases/manual", { method: "POST", body: JSON.stringify(payload) });
}

export function moveInsuranceCaseToStage(
  caseId: string,
  payload: { target: string; reason?: string; re_eligibility?: InsuranceReEligibilityChoice; re_eligible_date?: string },
) {
  return apiRequest<InsuranceCaseDetail>(`/insurance-cases/${caseId}/move-to-stage`, { method: "POST", body: JSON.stringify(payload) });
}

// ---------------------------------------------------------------- schema documents

export function listInsuranceCaseDocuments(caseId: string) {
  return apiRequest<InsuranceCaseDocument[]>(`/insurance-cases/${caseId}/documents`);
}

export function getInsuranceCaseDocumentHistory(caseId: string, documentTypeId: string) {
  return apiRequest<InsuranceCaseDocument[]>(`/insurance-cases/${caseId}/documents/${documentTypeId}/history`);
}

export function verifyInsuranceCaseDocument(caseId: string, documentId: string) {
  return apiRequest<InsuranceCaseDocument>(`/insurance-cases/${caseId}/documents/${documentId}/verify`, { method: "POST" });
}

export function rejectInsuranceCaseDocument(caseId: string, documentId: string, reason: string) {
  return apiRequest<InsuranceCaseDocument>(`/insurance-cases/${caseId}/documents/${documentId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// ---------------------------------------------------------------- "Add Other Document" (ad-hoc, per-case)

export function listOtherDocuments(caseId: string) {
  return apiRequest<OtherDocument[]>(`/insurance-cases/${caseId}/other-documents`);
}

export function addOtherDocument(caseId: string, name: string) {
  return apiRequest<OtherDocument>(`/insurance-cases/${caseId}/other-documents`, { method: "POST", body: JSON.stringify({ name }) });
}

export function verifyOtherDocument(caseId: string, docId: string) {
  return apiRequest<OtherDocument>(`/insurance-cases/${caseId}/other-documents/${docId}/verify`, { method: "POST" });
}

export function rejectOtherDocument(caseId: string, docId: string, reason: string) {
  return apiRequest<OtherDocument>(`/insurance-cases/${caseId}/other-documents/${docId}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function listOwnOtherDocuments(caseId: string) {
  return apiRequest<OtherDocument[]>(`/insurance-cases/mine/${caseId}/other-documents`);
}

async function putOtherDocumentToStorage(uploadUrl: string, file: File): Promise<void> {
  let response: Response;
  try {
    response = await fetch(uploadUrl, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
  } catch (err) {
    throw new ApiError("document_upload_failed", "Document upload failed. Please try again.", err);
  }
  if (!response.ok) {
    throw new ApiError("document_upload_failed", "Document upload failed. Please try again.", {
      status: response.status,
      statusText: response.statusText,
    });
  }
}

export async function uploadOwnOtherDocument(caseId: string, docId: string, file: File): Promise<OtherDocument> {
  const { upload_url } = await apiRequest<{ upload_url: string; s3_key: string }>(
    `/insurance-cases/mine/${caseId}/other-documents/${docId}/upload-url`,
    { method: "POST", body: JSON.stringify({ file_name: file.name, content_type: file.type || undefined }) },
  );
  await putOtherDocumentToStorage(upload_url, file);
  return apiRequest<OtherDocument>(`/insurance-cases/mine/${caseId}/other-documents/${docId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ file_name: file.name, content_type: file.type || undefined }),
  });
}
