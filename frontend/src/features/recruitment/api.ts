import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

// Insurance Advisor Recruitment — a second workflow inside Insurance Management.
// Mirrors the shape/conventions of features/insurance_management/api.ts.

export type RecruitmentStage =
  | "fresh"
  | "bop"
  | "doc_collection"
  | "exam_fee_status"
  | "examination"
  | "re_examination"
  | "advisor"
  | "rejected";

export type ExaminationOutcome = "pass" | "fail" | "absent";
export type SignatureMethod = "draw" | "type" | "upload";
export type BankProofType = "cheque" | "passbook";

export const GENDERS = ["male", "female", "other"] as const;
export const PROFESSIONS = ["house_wife", "retired", "self_employed", "salaried", "other"] as const;
export const NOMINEE_RELATIONSHIPS = [
  "spouse",
  "father",
  "mother",
  "son",
  "daughter",
  "brother",
  "sister",
  "other",
] as const;

export const DOCUMENT_SLOTS = ["pan", "aadhaar", "bank_proof", "qualification", "photo", "signature"] as const;
export type DocumentSlot = (typeof DOCUMENT_SLOTS)[number];

export interface RecruitmentLeadListItem {
  id: string;
  recruitment_code: string;
  full_name: string;
  mobile: string;
  email: string | null;
  gender: string;
  age: number;
  source_id: string;
  source_name: string;
  profession: string;
  other_profession: string | null;
  remarks: string | null;
  stage: RecruitmentStage;
  assigned_to: string | null;
  assigned_to_name: string | null;
  latest_examination_result: ExaminationOutcome | null;
  documents_ready: boolean;
  advisor_id: string | null;
  rejected_reason: string | null;
  rejected_at: string | null;
  created_at: string;
}

export interface RecruitmentDocumentFile {
  file_name: string;
  uploaded_at: string;
  download_url: string | null;
}

export interface RecruitmentDocuments {
  pan: RecruitmentDocumentFile | null;
  aadhaar: RecruitmentDocumentFile | null;
  bank_proof: RecruitmentDocumentFile | null;
  bank_proof_type: BankProofType | null;
  cheque_name_confirmed: boolean;
  qualification: RecruitmentDocumentFile | null;
  photo: RecruitmentDocumentFile | null;
  email: string | null;
  mobile: string | null;
  alternate_number: string | null;
  nominee: { name: string; dob: string; relationship: string } | null;
  signature: { method: SignatureMethod; value: string; file_name: string | null } | null;
}

export interface ExaminationResult {
  attempt: number;
  result: ExaminationOutcome;
  remarks: string | null;
  recorded_by: string | null;
  recorded_at: string;
}

export interface RecruitmentLeadDetail extends RecruitmentLeadListItem {
  updated_at: string;
  assigned_by: string | null;
  assigned_at: string | null;
  exam_fee_paid: boolean;
  exam_fee_paid_at: string | null;
  exam_fee_reference: string | null;
  documents: RecruitmentDocuments | null;
  examinations: ExaminationResult[];
}

export interface RecruitmentCounts {
  fresh: number;
  bop: number;
  doc_collection: number;
  exam_fee_status: number;
  examination: number;
  re_examination: number;
  agency_code: number;
  rejected: number;
}

export interface RecruitmentTimelineEntry {
  type: "activity" | "note";
  event_type: string | null;
  text: string | null;
  metadata: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string;
}

export interface AdvisorSummary {
  id: string;
  advisor_code: string;
  recruitment_lead_id: string;
  full_name: string;
  mobile: string;
  email: string | null;
  channel: string;
  agency_code: string | null;
  agent_code: string | null;
  status: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

const BASE = "/recruitment-leads";

export async function listRecruitmentLeads(params: {
  page?: number;
  page_size?: number;
  search?: string;
  stage?: string;
  assigned_to?: string;
}): Promise<PaginatedResponse<RecruitmentLeadListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<RecruitmentLeadListItem[]>(`${BASE}${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getRecruitmentCounts() {
  return apiRequest<RecruitmentCounts>(`${BASE}/counts`);
}

export function getRecruitmentLookup() {
  return apiRequest<{ sources: { id: string; name: string }[] }>(`${BASE}/lookup`);
}

export function getRecruitmentLead(id: string) {
  return apiRequest<RecruitmentLeadDetail>(`${BASE}/${id}`);
}

export interface RecruitmentLeadInput {
  full_name: string;
  mobile: string;
  email?: string | null;
  gender: string;
  age: number;
  source_id: string;
  profession: string;
  other_profession?: string | null;
  remarks?: string | null;
}

export function createRecruitmentLead(payload: RecruitmentLeadInput) {
  return apiRequest<RecruitmentLeadDetail>(BASE, { method: "POST", body: JSON.stringify(payload) });
}

export function updateRecruitmentLead(id: string, payload: Partial<RecruitmentLeadInput>) {
  return apiRequest<RecruitmentLeadDetail>(`${BASE}/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

const post = (id: string, action: string, body?: unknown) =>
  apiRequest<RecruitmentLeadDetail>(`${BASE}/${id}/${action}`, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const moveRecruitmentToBop = (id: string) => post(id, "move-to-bop");
export const moveRecruitmentBackToFresh = (id: string) => post(id, "back-to-fresh");
export const moveRecruitmentToDocCollection = (id: string) => post(id, "move-to-doc-collection");
export const rejectRecruitmentLead = (id: string, reason: string) => post(id, "reject", { reason });
export const moveRecruitmentToAdvisor = (id: string) => post(id, "move-to-advisor");
export const assignRecruitmentLead = (id: string, employeeId: string) => post(id, "assign", { employee_id: employeeId });

export const recordRecruitmentExamination = (id: string, payload: { result: ExaminationOutcome; remarks?: string }) =>
  post(id, "examination", payload);

export const recordRecruitmentExamFee = (id: string, payload: { reference?: string }) =>
  post(id, "exam-fee", payload);

export function getRecruitmentDocumentUploadUrl(
  id: string,
  payload: { slot: DocumentSlot; file_name: string; content_type?: string },
) {
  return apiRequest<{ upload_url: string; s3_key: string }>(`${BASE}/${id}/documents/upload-url`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface SaveDocumentsPayload {
  pan?: { s3_key: string; file_name: string };
  aadhaar?: { s3_key: string; file_name: string };
  bank_proof?: { s3_key: string; file_name: string };
  bank_proof_type?: BankProofType;
  cheque_name_confirmed?: boolean;
  qualification?: { s3_key: string; file_name: string };
  photo?: { s3_key: string; file_name: string };
  email?: string;
  mobile?: string;
  alternate_number?: string;
  nominee?: { name: string; dob: string; relationship: string };
  signature?: { method: SignatureMethod; value: string; file_name?: string };
}

export function saveRecruitmentDocuments(id: string, payload: SaveDocumentsPayload) {
  return apiRequest<RecruitmentLeadDetail>(`${BASE}/${id}/documents`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getRecruitmentTimeline(id: string) {
  return apiRequest<RecruitmentTimelineEntry[]>(`${BASE}/${id}/timeline`);
}

export function getRecruitmentLeadAdvisor(id: string) {
  return apiRequest<AdvisorSummary | null>(`${BASE}/${id}/advisor`);
}

// ---------------------------------------------------------------- Advisor Management (Phase 2)

export const ADVISOR_PRODUCT_CATEGORIES = [
  "savings",
  "protection",
  "ulip",
  "annuity",
  "business_insurance",
  "custom",
] as const;
export type AdvisorProductCategory = (typeof ADVISOR_PRODUCT_CATEGORIES)[number];

export interface AdvisorListItem {
  id: string;
  advisor_code: string;
  recruitment_lead_id: string;
  full_name: string;
  mobile: string;
  email: string | null;
  channel: "qr" | "non_qr";
  agency_code: string | null;
  agent_code: string | null;
  // Profession classification — separate from `channel` (Type) and `status`. `null` for
  // advisors promoted before the field existed (the UI shows "—").
  profession: string | null;
  other_profession: string | null;
  status: "active" | "inactive";
  is_employee: boolean;
  no_of_policies: number;
  total_premium: number;
  created_at: string;
  // Whether an advisor-portal password has ever been set — NEVER the hash or plaintext
  // itself. Lets the UI show a safe masked "Password set" / "Not set" state.
  has_password: boolean;
}

export interface AdvisorBusinessRecord {
  id: string;
  advisor_id: string;
  customer_name: string | null;
  customer_mobile: string | null;
  policy_number: string | null;
  product_category: AdvisorProductCategory;
  custom_category: string | null;
  product_name: string;
  premium: number;
  ppt: number;
  pt: number;
  policy_issue_date: string;
  comment: string | null;
  created_at: string;
}

export interface AdvisorDetail extends AdvisorListItem {
  updated_at: string;
  recruitment: RecruitmentLeadDetail | null;
  businesses: AdvisorBusinessRecord[];
}

export async function listAdvisors(params: {
  page?: number;
  page_size?: number;
  search?: string;
  // The three independent filters. Omit one to mean "All".
  profession?: string;
  channel?: "qr" | "non_qr";
  status?: "active" | "inactive";
}): Promise<PaginatedResponse<AdvisorListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<AdvisorListItem[]>(`/advisors${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getAdvisor(id: string) {
  return apiRequest<AdvisorDetail>(`/advisors/${id}`);
}

export function updateAdvisor(
  id: string,
  payload: {
    agency_code?: string;
    agent_code?: string;
    channel?: "qr" | "non_qr";
    password?: string;
    status?: "active" | "inactive";
  },
) {
  return apiRequest<AdvisorDetail>(`/advisors/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function listAdvisorBusiness(id: string) {
  return apiRequest<AdvisorBusinessRecord[]>(`/advisors/${id}/business`);
}

export interface AddBusinessPayload {
  customer_name?: string;
  customer_mobile?: string;
  policy_number?: string;
  product_category: AdvisorProductCategory;
  custom_category?: string;
  product_name: string;
  premium: number;
  ppt: number;
  pt: number;
  policy_issue_date: string;
  comment?: string;
}

export function addAdvisorBusiness(id: string, payload: AddBusinessPayload) {
  return apiRequest<AdvisorBusinessRecord>(`/advisors/${id}/business`, { method: "POST", body: JSON.stringify(payload) });
}

// Uploads a Blob/File straight to S3 via the presigned PUT, then returns the confirmed
// { s3_key, file_name } the save endpoint expects.
export async function uploadRecruitmentFile(
  id: string,
  slot: DocumentSlot,
  file: Blob,
  fileName: string,
): Promise<{ s3_key: string; file_name: string }> {
  const { upload_url, s3_key } = await getRecruitmentDocumentUploadUrl(id, {
    slot,
    file_name: fileName,
    content_type: file.type || "application/octet-stream",
  });
  const res = await fetch(upload_url, {
    method: "PUT",
    body: file,
    headers: file.type ? { "Content-Type": file.type } : undefined,
  });
  if (!res.ok) throw new Error("Upload failed — please try again.");
  return { s3_key, file_name: fileName };
}
