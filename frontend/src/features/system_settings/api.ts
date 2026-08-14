// Module 4 — Settings (Master Data) typed API client.
import { apiRequest } from "@/shared/api/client";

export interface NamedMasterData {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface MasterDataItem {
  id: string;
  name: string;
  description: string | null;
  status: string;
}

export interface Address {
  line1: string;
  line2?: string | null;
  city: string;
  state: string;
  pincode: string;
  country?: string;
}

export interface Branch {
  id: string;
  name: string;
  code: string;
  address: Address | null;
  phone: string | null;
  status: string;
}

export interface StatusMaster {
  id: string;
  category: string;
  name: string;
  sequence: number;
  description: string | null;
  status: string;
}

export interface NotificationTemplate {
  id: string;
  channel: string;
  key: string;
  subject: string | null;
  body: string;
  available_variables: string[];
  status: string;
}

export interface ApiSetting {
  id: string;
  provider: string;
  label: string;
  configured_keys: string[];
  is_enabled: boolean;
  status: string;
  updated_at: string;
}

export interface BusinessHour {
  day: string;
  is_closed: boolean;
  open_time: string | null;
  close_time: string | null;
}

export interface CompanySettings {
  id: string;
  company_name: string;
  logo_s3_key: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  business_hours: BusinessHour[];
  contact_email: string | null;
  contact_phone: string | null;
  address: Address | null;
  updated_at: string;
}

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

// ---- generic named master data (Lead Sources / Loan Products / Insurance Products / Document Types) ----

function namedMasterDataApi(basePath: string) {
  return {
    list: () => apiRequest<NamedMasterData[]>(basePath),
    create: (name: string, description?: string) =>
      apiRequest<NamedMasterData>(basePath, { method: "POST", body: JSON.stringify({ name, description }) }),
    update: (id: string, payload: { name?: string; description?: string }) =>
      apiRequest<NamedMasterData>(`${basePath}/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    activate: (id: string) => apiRequest<NamedMasterData>(`${basePath}/${id}/activate`, { method: "PATCH" }),
    deactivate: (id: string) => apiRequest<NamedMasterData>(`${basePath}/${id}/deactivate`, { method: "PATCH" }),
  };
}

export const leadSourcesApi = namedMasterDataApi("/lead-sources");
export const loanProductsApi = namedMasterDataApi("/loan-products");
export const insuranceProductsApi = namedMasterDataApi("/insurance-products");
export const documentTypesApi = namedMasterDataApi("/document-types");

// ---- departments / designations (Module 2 owns create/list; Module 4 adds edit/activate/deactivate) ----

export function listDepartments() {
  return apiRequest<MasterDataItem[]>("/departments");
}
export function createDepartment(name: string, description?: string) {
  return apiRequest<MasterDataItem>("/departments", { method: "POST", body: JSON.stringify({ name, description }) });
}
export function updateDepartment(id: string, payload: { name?: string; description?: string }) {
  return apiRequest<MasterDataItem>(`/departments/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateDepartment(id: string) {
  return apiRequest<MasterDataItem>(`/departments/${id}/activate`, { method: "PATCH" });
}
export function deactivateDepartment(id: string) {
  return apiRequest<MasterDataItem>(`/departments/${id}/deactivate`, { method: "PATCH" });
}

export function listDesignations() {
  return apiRequest<MasterDataItem[]>("/designations");
}
export function createDesignation(name: string, description?: string) {
  return apiRequest<MasterDataItem>("/designations", { method: "POST", body: JSON.stringify({ name, description }) });
}
export function updateDesignation(id: string, payload: { name?: string; description?: string }) {
  return apiRequest<MasterDataItem>(`/designations/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateDesignation(id: string) {
  return apiRequest<MasterDataItem>(`/designations/${id}/activate`, { method: "PATCH" });
}
export function deactivateDesignation(id: string) {
  return apiRequest<MasterDataItem>(`/designations/${id}/deactivate`, { method: "PATCH" });
}

// ---- branches ----

export function listBranches() {
  return apiRequest<Branch[]>("/branches");
}
export function createBranch(payload: { name: string; code: string; phone?: string; address?: Address }) {
  return apiRequest<Branch>("/branches", { method: "POST", body: JSON.stringify(payload) });
}
export function updateBranch(id: string, payload: { name?: string; code?: string; phone?: string; address?: Address }) {
  return apiRequest<Branch>(`/branches/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateBranch(id: string) {
  return apiRequest<Branch>(`/branches/${id}/activate`, { method: "PATCH" });
}
export function deactivateBranch(id: string) {
  return apiRequest<Branch>(`/branches/${id}/deactivate`, { method: "PATCH" });
}

// ---- status masters ----

export function listStatusMasters(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return apiRequest<StatusMaster[]>(`/status-masters${qs}`);
}
export function createStatusMaster(payload: { category: string; name: string; sequence?: number; description?: string }) {
  return apiRequest<StatusMaster>("/status-masters", { method: "POST", body: JSON.stringify(payload) });
}
export function updateStatusMaster(id: string, payload: { name?: string; sequence?: number; description?: string }) {
  return apiRequest<StatusMaster>(`/status-masters/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateStatusMaster(id: string) {
  return apiRequest<StatusMaster>(`/status-masters/${id}/activate`, { method: "PATCH" });
}
export function deactivateStatusMaster(id: string) {
  return apiRequest<StatusMaster>(`/status-masters/${id}/deactivate`, { method: "PATCH" });
}

// ---- notification templates ----

export function listNotificationTemplates(channel?: string) {
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : "";
  return apiRequest<NotificationTemplate[]>(`/notification-templates${qs}`);
}
export function createNotificationTemplate(payload: { channel: string; key: string; subject?: string; body: string }) {
  return apiRequest<NotificationTemplate>("/notification-templates", { method: "POST", body: JSON.stringify(payload) });
}
export function updateNotificationTemplate(id: string, payload: { subject?: string; body?: string }) {
  return apiRequest<NotificationTemplate>(`/notification-templates/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateNotificationTemplate(id: string) {
  return apiRequest<NotificationTemplate>(`/notification-templates/${id}/activate`, { method: "PATCH" });
}
export function deactivateNotificationTemplate(id: string) {
  return apiRequest<NotificationTemplate>(`/notification-templates/${id}/deactivate`, { method: "PATCH" });
}

// ---- API settings ----

export function listApiSettings() {
  return apiRequest<ApiSetting[]>("/api-settings");
}
export function createApiSetting(payload: { provider: string; label: string; config: Record<string, string> }) {
  return apiRequest<ApiSetting>("/api-settings", { method: "POST", body: JSON.stringify(payload) });
}
export function updateApiSetting(id: string, payload: { label?: string; config?: Record<string, string> }) {
  return apiRequest<ApiSetting>(`/api-settings/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}
export function activateApiSetting(id: string) {
  return apiRequest<ApiSetting>(`/api-settings/${id}/activate`, { method: "PATCH" });
}
export function deactivateApiSetting(id: string) {
  return apiRequest<ApiSetting>(`/api-settings/${id}/deactivate`, { method: "PATCH" });
}

// ---- company settings (singleton) ----

export function getCompanySettings() {
  return apiRequest<CompanySettings>("/company-settings");
}
export function updateCompanySettings(payload: {
  company_name?: string;
  primary_color?: string;
  secondary_color?: string;
  business_hours?: BusinessHour[];
  contact_email?: string;
  contact_phone?: string;
  address?: Address;
}) {
  return apiRequest<CompanySettings>("/company-settings", { method: "PATCH", body: JSON.stringify(payload) });
}
export function getLogoUploadUrl() {
  return apiRequest<{ upload_url: string; s3_key: string }>("/company-settings/logo/upload-url", { method: "POST" });
}
export function confirmLogo(s3Key: string) {
  return apiRequest<CompanySettings>("/company-settings/logo", { method: "PATCH", body: JSON.stringify({ s3_key: s3Key }) });
}
