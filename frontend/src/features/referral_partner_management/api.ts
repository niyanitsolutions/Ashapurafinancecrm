import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface ReferralPartner {
  id: string;
  partner_code: string;
  full_name: string;
  mobile: string;
  email: string | null;
  business_name: string | null;
  approval_status: string;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReferralLead {
  lead_id: string;
  lead_code: string;
  full_name: string;
  mobile: string;
  product_category: string;
  product_id: string;
  external_status: string;
  editable: boolean;
  submitted_at: string;
}

export interface CommissionRule {
  id: string;
  label: string;
  product_category: string | null;
  partner_id: string | null;
  calculation_type: string;
  rate_or_amount: number;
  trigger_event: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CommissionEntry {
  id: string;
  partner_id: string;
  partner_name: string | null;
  lead_id: string;
  case_type: string;
  case_id: string;
  rule_id: string;
  calculation_type: string;
  rate_or_amount: number;
  base_amount: number;
  commission_amount: number;
  status: string;
  approved_at: string | null;
  paid_at: string | null;
  payment_reference: string | null;
  created_at: string;
}

export interface ReferralDashboard {
  total_leads: number;
  approved_leads: number;
  rejected_leads: number;
  commission_pending: number;
  commission_approved: number;
  commission_paid: number;
  commission_balance: number;
  recent_leads: ReferralLead[];
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

// ---- Owner: partner lifecycle ----

export function createReferralPartner(payload: { full_name: string; mobile: string; email?: string; business_name?: string }) {
  return apiRequest<ReferralPartner>("/referral-partners", { method: "POST", body: JSON.stringify(payload) });
}

export async function listReferralPartners(params: { page?: number; page_size?: number; search?: string; approval_status?: string }): Promise<PaginatedResponse<ReferralPartner>> {
  const envelope = await apiRequestRaw<ReferralPartner[]>(`/referral-partners${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function approveReferralPartner(partnerId: string) {
  return apiRequest<ReferralPartner>(`/referral-partners/${partnerId}/approve`, { method: "POST" });
}

export function deactivateReferralPartner(partnerId: string) {
  return apiRequest<ReferralPartner>(`/referral-partners/${partnerId}/deactivate`, { method: "POST" });
}

// ---- Owner: commission rules ----

export function createCommissionRule(payload: {
  label: string; product_category?: string; partner_id?: string; calculation_type: string; rate_or_amount: number; trigger_event: string;
}) {
  return apiRequest<CommissionRule>("/commission-rules", { method: "POST", body: JSON.stringify(payload) });
}

export function listCommissionRules() {
  return apiRequest<CommissionRule[]>("/commission-rules");
}

export function updateCommissionRule(ruleId: string, payload: Record<string, unknown>) {
  return apiRequest<CommissionRule>(`/commission-rules/${ruleId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function activateCommissionRule(ruleId: string) {
  return apiRequest<CommissionRule>(`/commission-rules/${ruleId}/activate`, { method: "PATCH" });
}

export function deactivateCommissionRule(ruleId: string) {
  return apiRequest<CommissionRule>(`/commission-rules/${ruleId}/deactivate`, { method: "PATCH" });
}

// ---- Owner: commission ledger ----

export async function listCommissionEntries(params: { page?: number; page_size?: number; partner_id?: string; status?: string }): Promise<PaginatedResponse<CommissionEntry>> {
  const envelope = await apiRequestRaw<CommissionEntry[]>(`/commission-entries${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function approveCommissionEntry(entryId: string) {
  return apiRequest<CommissionEntry>(`/commission-entries/${entryId}/approve`, { method: "POST" });
}

export function settleCommissionEntry(entryId: string, paymentReference: string) {
  return apiRequest<CommissionEntry>(`/commission-entries/${entryId}/settle`, { method: "POST", body: JSON.stringify({ payment_reference: paymentReference }) });
}

// ---- Referral Partner: self-service ----

export function getOwnPartner() {
  return apiRequest<ReferralPartner>("/referral-partners/me");
}

export interface ReferralProductOption {
  id: string;
  name: string;
  description: string | null;
}

export function listOwnAddLeadProducts(category: "loan" | "insurance") {
  return apiRequest<ReferralProductOption[]>(`/referral-partners/me/products?category=${category}`);
}

export function addReferralLead(payload: {
  full_name: string;
  mobile: string;
  email?: string;
  product_category: string;
  product_id: string;
  remarks?: string;
  product_form_data?: Record<string, unknown>;
}) {
  return apiRequest<ReferralLead>("/referral-partners/me/leads", { method: "POST", body: JSON.stringify(payload) });
}

export function updateReferralLead(leadId: string, payload: { full_name?: string; mobile?: string; email?: string; remarks?: string }) {
  return apiRequest<ReferralLead>(`/referral-partners/me/leads/${leadId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listOwnLeads(params: { page?: number; page_size?: number }): Promise<PaginatedResponse<ReferralLead>> {
  const envelope = await apiRequestRaw<ReferralLead[]>(`/referral-partners/me/leads${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getOwnDashboard() {
  return apiRequest<ReferralDashboard>("/referral-partners/me/dashboard");
}

export async function listOwnCommissionEntries(params: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<CommissionEntry>> {
  const envelope = await apiRequestRaw<CommissionEntry[]>(`/referral-partners/me/commission-entries${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}
