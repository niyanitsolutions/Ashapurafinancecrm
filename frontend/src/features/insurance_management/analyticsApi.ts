import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface AnalyticsFilters { [key: string]: string | undefined; date_from?: string; date_to?: string; advisor_id?: string; product_id?: string; stage?: string }
export interface AnalyticsOverview {
  capabilities: { advisor_business: boolean; policy_pipeline: boolean };
  summary: { total_advisors: number | null; total_business: number | null; business_premium: number | null; total_policy_leads: number | null; total_policy_issued: number | null; policy_premium: number | null };
  pipeline: { stage: string; count: number }[];
  stages: string[];
  advisors: { id: string; label: string }[];
  products: { id: string; label: string }[];
}
export interface AdvisorAnalyticsRow { advisor_id: string; advisor_code: string; advisor_name: string; businesses: number; total_premium: number; products: number }
export interface AdvisorBusinessItem { id: string; customer_name: string | null; customer_mobile: string | null; policy_number: string | null; product_name: string; product_category: string; premium: number; ppt: number; pt: number; policy_issue_date: string; comment: string | null; created_at: string }
export interface AdvisorWork { advisor: AdvisorAnalyticsRow; products: { product_name: string; businesses: number }[]; businesses: AdvisorBusinessItem[] }
export interface ProductAnalyticsRow { product_id: string; product_name: string; leads: number; issued: number; premium: number }
export interface PolicyAnalyticsItem { id: string; case_code: string; customer_id: string; customer_name: string | null; advisor_id: string | null; advisor_name: string | null; product_id: string; product_name: string; stage: string; premium: number | null; created_at: string }
export interface ProductWork { product: ProductAnalyticsRow; leads: PolicyAnalyticsItem[] }

function query(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") usp.set(key, String(value)); });
  const value = usp.toString();
  return value ? `?${value}` : "";
}

export const getAnalyticsOverview = (filters: AnalyticsFilters) => apiRequest<AnalyticsOverview>(`/insurance-analytics/overview${query(filters)}`);

async function paged<T>(path: string, params: Record<string, string | number | undefined>): Promise<{ data: T[]; pagination: PaginationMeta | null }> {
  const response = await apiRequestRaw<T[]>(`${path}${query(params)}`);
  return { data: response.data ?? [], pagination: response.meta?.pagination ?? null };
}

export const listAdvisorAnalytics = (filters: AnalyticsFilters, page = 1) => paged<AdvisorAnalyticsRow>("/insurance-analytics/advisors", { ...filters, product_id: undefined, stage: undefined, page, page_size: 10 });
export async function getAdvisorWork(id: string, filters: AnalyticsFilters, page = 1): Promise<{ data: AdvisorWork; pagination: PaginationMeta | null }> {
  const response = await apiRequestRaw<AdvisorWork>(`/insurance-analytics/advisors/${id}${query({ date_from: filters.date_from, date_to: filters.date_to, page, page_size: 10 })}`);
  if (!response.data) throw new Error("Advisor analytics response was empty.");
  return { data: response.data, pagination: response.meta?.pagination ?? null };
}
export const listProductAnalytics = (filters: AnalyticsFilters, page = 1) => paged<ProductAnalyticsRow>("/insurance-analytics/products", { ...filters, page, page_size: 10 });
export async function getProductWork(id: string, filters: AnalyticsFilters, page = 1): Promise<{ data: ProductWork; pagination: PaginationMeta | null }> {
  const response = await apiRequestRaw<ProductWork>(`/insurance-analytics/products/${id}${query({ date_from: filters.date_from, date_to: filters.date_to, advisor_id: filters.advisor_id, stage: filters.stage, page, page_size: 10 })}`);
  if (!response.data) throw new Error("Product analytics response was empty.");
  return { data: response.data, pagination: response.meta?.pagination ?? null };
}
