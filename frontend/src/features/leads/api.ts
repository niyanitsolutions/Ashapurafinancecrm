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
  is_potential_duplicate: boolean;
  created_at: string;
}

export interface LeadDetail extends LeadListItem {
  remarks: string | null;
  city: string | null;
  preferred_amount: number | null;
  duplicate_of_lead_ids: string[];
  updated_at: string;
  form_definition_id: string | null;
  product_form_data: Record<string, unknown> | null;
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
  // Populated when the selected product has a Product Schema and Create Lead rendered
  // its Basic Information fields (see useProductSchema / ProductSchemaForm) — omit
  // entirely for a product with no schema yet, same as before this field existed.
  product_form_data?: Record<string, unknown>;
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
// filter by assignment presence (for the New Leads / Assigned Leads tabs) without a new
// query param or any change to assign/unassign behavior.
export const UNASSIGNED_SENTINEL = "__unassigned__";
export const ASSIGNED_SENTINEL = "__assigned__";

export interface LeadListParams {
  page?: number;
  page_size?: number;
  search?: string;
  source_id?: string;
  product_category?: string;
  product_id?: string;
  assigned_to?: string;
  status?: string;
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

export function getLead(leadId: string) {
  return apiRequest<LeadDetail>(`/leads/${leadId}`);
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
