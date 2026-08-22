import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface LeadListItem {
  id: string;
  lead_code: string;
  full_name: string;
  mobile: string;
  email: string | null;
  source_id: string;
  source_name: string;
  product_category: string;
  product_id: string;
  product_name: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  status: string;
  // Leads workflow redesign, Phase 1 (decision 125) — SEPARATE from `status` above.
  stage: "fresh" | "assigned" | "document_collection" | "rejected" | "loan_management";
  salary_in_hand: number | null;
  next_follow_up_date: string | null;
  assigned_by: string | null;
  assigned_by_name: string | null;
  assigned_at: string | null;
  rejected_reason: string | null;
  rejected_by: string | null;
  rejected_by_name: string | null;
  rejected_at: string | null;
  // Phase 3 (decision 127) — read-only enrichment from the existing Application entity
  // (Module 6B), populated only for Document Collection tab list responses; null
  // everywhere else, including when no Application exists yet for a Document
  // Collection lead (a legitimate "Pending" state, not an error).
  application_id: string | null;
  application_status: "draft" | "submitted" | null;
  is_potential_duplicate: boolean;
  created_at: string;
}

// My Leads' Update screen — financial/customer assessment (Phase 2, decision 125). A
// single embedded snapshot, not a history — each save wholesale-replaces the previous
// one, unlike Comment History's append-only LeadNotes.
export interface LeadFinancialAssessment {
  mock_off_salary: number | null;
  salary_mode: "account" | "cash" | "cheque" | null;
  emi_range: string | null;
  total_experience: string | null;
  current_company_experience: string | null;
  company_location: string | null;
  any_loan: boolean | null;
  last_3_months_salary: "same" | "hiked" | "decreased" | "partial" | null;
  cibil_score: number | null;
  cibil_unknown: boolean;
  remarks: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface LeadDetail extends LeadListItem {
  remarks: string | null;
  city: string | null;
  preferred_amount: number | null;
  duplicate_of_lead_ids: string[];
  updated_at: string;
  form_definition_id: string | null;
  product_form_data: Record<string, unknown> | null;
  // Phase 2 (decision 125) — only present on the detail response, not the list.
  financial_assessment: LeadFinancialAssessment | null;
  account_created: boolean;
  // Phase 3 (decision 127) — document-completion summary against the linked
  // Application's required documents; zeros/false when no Application exists yet.
  documents_required: number;
  documents_verified: number;
  all_documents_verified: boolean;
}

export interface LeadCounts {
  fresh: number;
  my_leads: number;
  document_collection: number;
  rejected: number;
  assigned: number;
}

export interface CreateLeadInput {
  full_name: string;
  mobile: string;
  email?: string;
  source_id: string;
  product_category: "loan" | "insurance";
  product_id: string;
  remarks?: string;
  city?: string;
  preferred_amount?: number;
  salary_in_hand?: number;
  // "YYYY-MM-DD" (IST calendar date) — see @/shared/dateFormat.
  next_follow_up_date?: string;
  // Seeds the lead's first Comment History entry (LeadNote) — omit for none.
  comment?: string;
  // Employee id, or SELF_SENTINEL below — omit to leave the lead unassigned.
  assigned_to?: string;
  // Populated when the selected product has a Product Schema and Create Lead rendered
  // its Basic Information fields (see useProductSchema / ProductSchemaForm) — omit
  // entirely for a product with no schema yet, same as before this field existed.
  product_form_data?: Record<string, unknown>;
  // Best-effort browser geolocation (see @/shared/geolocation) — only checked server-side
  // when a Geo Fence is configured for lead_creation; omitting these behaves exactly as
  // before this field existed.
  latitude?: number;
  longitude?: number;
}

export type UpdateLeadInput = Partial<CreateLeadInput>;

export interface NoteEntry {
  id: string;
  lead_id: string;
  text: string;
  created_by: string | null;
  created_at: string;
}

export interface TimelineEntry {
  type: "activity" | "note";
  event_type?: string | null;
  text?: string | null;
  metadata?: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

// Sentinel values for `assigned_to`, matching backend/app/features/leads/repository.py —
// filter by assignment presence (for the Fresh Leads / My Leads / Assigned tabs) without
// a new query param or any change to assign/unassign behavior.
export const UNASSIGNED_SENTINEL = "__unassigned__";
export const ASSIGNED_SENTINEL = "__assigned__";
// "The acting employee themselves" — resolved server-side, never a literal employee id
// the frontend has to know. Backs the My Leads tab and Create/Edit Lead's "Assign To:
// Self" option (decision 125).
export const SELF_SENTINEL = "__self__";

export interface LeadListParams {
  page?: number;
  page_size?: number;
  search?: string;
  source_id?: string;
  product_category?: string;
  product_id?: string;
  assigned_to?: string;
  status?: string;
  stage?: string;
  exclude_stage?: string;
}

function toQuery(params: LeadListParams): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export async function listLeads(params: LeadListParams): Promise<PaginatedResponse<LeadListItem>> {
  const envelope = await apiRequestRaw<LeadListItem[]>(`/leads${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getLeadCounts() {
  return apiRequest<LeadCounts>("/leads/counts");
}

export function getLead(leadId: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}`);
}

export interface LeadLookupData {
  sources: { id: string; name: string }[];
  loan_products: { id: string; name: string }[];
  insurance_products: { id: string; name: string }[];
}

// Backs the Create Lead form's Source/Product dropdowns — gated on leads:leads:view,
// not system_settings's own CRUD-permission-gated lead-sources/loan-products/
// insurance-products endpoints (which would otherwise require also granting Settings
// administration access just to populate a dropdown). See backend leads/router.py.
export function getLeadLookup() {
  return apiRequest<LeadLookupData>("/leads/lookup");
}

export function createLead(payload: CreateLeadInput) {
  return apiRequest<LeadDetail>("/leads", { method: "POST", body: JSON.stringify(payload) });
}

export function updateLead(leadId: string, payload: UpdateLeadInput) {
  return apiRequest<LeadDetail>(`/leads/${leadId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function checkDuplicate(mobile: string) {
  return apiRequest<{ matches: LeadListItem[] }>(`/leads/check-duplicate?mobile=${encodeURIComponent(mobile)}`);
}

export function assignLead(leadId: string, employeeId: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/assign`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) });
}

export function unassignLead(leadId: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/unassign`, { method: "POST" });
}

export function rejectLead(leadId: string, reason: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/reject`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function setLeadStage(leadId: string, stage: "assigned" | "document_collection" | "loan_management") {
  return apiRequest<LeadDetail>(`/leads/${leadId}/stage`, { method: "POST", body: JSON.stringify({ stage }) });
}

export function setFollowUp(leadId: string, nextFollowUpDate: string, comment?: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/follow-up`, {
    method: "POST",
    body: JSON.stringify({ next_follow_up_date: nextFollowUpDate, comment: comment || undefined }),
  });
}

// Whole-object replace, not a partial merge — always send the full current form state
// (see backend LeadService.set_financial_assessment, Phase 2 / decision 125).
export type FinancialAssessmentInput = Omit<LeadFinancialAssessment, "updated_at" | "updated_by">;

export function updateFinancialAssessment(leadId: string, payload: FinancialAssessmentInput) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/financial-assessment`, { method: "PATCH", body: JSON.stringify(payload) });
}

// No phone_number param on purpose — the account's mobile is always the Lead's own
// mobile, enforced server-side (see CustomerService.create_staff_initiated_account).
export function createCustomerAccount(leadId: string, password: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}/customer-account`, { method: "POST", body: JSON.stringify({ password }) });
}

// Staff-initiated password reset for an already-created customer account (see backend
// CustomerService.reset_customer_password) — reuses the same hashing/session-revocation
// primitives as every other password-set path, no second auth mechanism.
export function resetCustomerPassword(leadId: string, newPassword: string, confirmPassword: string) {
  return apiRequest<{ success: boolean }>(`/leads/${leadId}/customer-account/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword }),
  });
}

export interface EligibleAssignee {
  id: string;
  display_name: string;
  designation_name: string;
  branch_name: string;
  current_lead_count: number;
  product_match: boolean;
  recommended: boolean;
}

// Active employees who have module access matching this lead's product category (e.g.
// "loan" -> Loan Management module) — see backend LeadService.list_eligible_assignees.
// Never the full unfiltered employee list, and never gated by a separate "assign"
// permission — module access alone determines eligibility.
export function listEligibleAssignees(productCategory: string, productId?: string) {
  const params = new URLSearchParams({ product_category: productCategory });
  if (productId) params.set("product_id", productId);
  return apiRequest<EligibleAssignee[]>(`/leads/eligible-assignees?${params}`);
}

export function getTimeline(leadId: string) {
  return apiRequest<TimelineEntry[]>(`/leads/${leadId}/timeline`);
}

export function addNote(leadId: string, text: string) {
  return apiRequest<NoteEntry>(`/leads/${leadId}/notes`, { method: "POST", body: JSON.stringify({ text }) });
}

export function exportLeadsCsvUrl(): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
  return `${base}/leads/export`;
}
