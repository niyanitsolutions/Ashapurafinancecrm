import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

export interface AddressInput {
  line1: string;
  line2?: string | null;
  city: string;
  state: string;
  pincode: string;
  country?: string;
}

export interface EmergencyContactInput {
  name: string;
  relationship: string;
  mobile: string;
}

export interface BankDetailsInput {
  account_holder_name: string;
  bank_name: string;
  branch_name: string;
  ifsc_code: string;
  account_number: string;
}

export interface EmployeeListItem {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  display_name: string;
  email: string;
  mobile: string;
  department_id: string;
  department_name: string;
  designation_id: string;
  designation_name: string;
  branch_id: string;
  branch_name: string;
  status: string;
  joining_date: string;
  product_ids: string[];
}

export interface EmployeeDetail extends EmployeeListItem {
  user_id: string;
  gender: string | null;
  date_of_birth: string | null;
  blood_group: string | null;
  photo_s3_key: string | null;
  alternative_mobile: string | null;
  emergency_contact: EmergencyContactInput | null;
  current_address: AddressInput | null;
  permanent_address: AddressInput | null;
  employment_type: string;
  reporting_manager_id: string | null;
  bank_details: { account_holder_name: string; bank_name: string; branch_name: string; ifsc_code: string; account_number_masked: string } | null;
  created_at: string;
  updated_at: string;
}

export interface CreateEmployeeInput {
  mobile: string;
  initial_password: string;
  first_name: string;
  last_name: string;
  display_name?: string;
  gender?: string;
  date_of_birth?: string;
  blood_group?: string;
  alternative_mobile?: string;
  email: string;
  emergency_contact?: EmergencyContactInput;
  current_address?: AddressInput;
  permanent_address?: AddressInput;
  department_id: string;
  designation_id: string;
  branch_id: string;
  joining_date: string;
  employment_type: string;
  reporting_manager_id?: string;
  bank_details?: BankDetailsInput;
  product_ids?: string[];
}

export type UpdateEmployeeInput = Partial<Omit<CreateEmployeeInput, "mobile" | "initial_password">> & { status?: string };

export type SelfUpdateEmployeeInput = Pick<
  Partial<CreateEmployeeInput>,
  "first_name" | "last_name" | "display_name" | "gender" | "date_of_birth" | "blood_group" | "alternative_mobile" | "emergency_contact" | "current_address" | "permanent_address"
>;

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

export interface SessionSummary {
  id: string;
  device: string | null;
  browser: string | null;
  operating_system: string | null;
  ip_address: string | null;
  city: string | null;
  country: string | null;
  login_at: string;
  last_activity_at: string;
  status: string;
}

export interface LoginHistoryEntry {
  event_type: string;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivitySummary {
  total_logins: number;
  failed_login_count: number;
  last_login_at: string | null;
  active_session_count: number;
  account_status: string;
  employment_status: string;
}

export interface MasterDataItem {
  id: string;
  name: string;
  description?: string | null;
  status: string;
}

export interface BranchItem extends MasterDataItem {
  code: string;
  phone?: string | null;
}

export interface EmployeeListParams {
  page?: number;
  page_size?: number;
  search?: string;
  department_id?: string;
  designation_id?: string;
  branch_id?: string;
  status?: string;
}

function toQuery(params: EmployeeListParams): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export async function listEmployees(params: EmployeeListParams): Promise<PaginatedResponse<EmployeeListItem>> {
  const envelope = await apiRequestRaw<EmployeeListItem[]>(`/employees${toQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getEmployee(employeeId: string) {
  return apiRequest<EmployeeDetail>(`/employees/${employeeId}`);
}

export function createEmployee(payload: CreateEmployeeInput) {
  return apiRequest<EmployeeDetail>("/employees", { method: "POST", body: JSON.stringify(payload) });
}

export function updateEmployee(employeeId: string, payload: UpdateEmployeeInput) {
  return apiRequest<EmployeeDetail>(`/employees/${employeeId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function activateEmployee(employeeId: string) {
  return apiRequest<EmployeeDetail>(`/employees/${employeeId}/activate`, { method: "PATCH" });
}

export function deactivateEmployee(employeeId: string) {
  return apiRequest<EmployeeDetail>(`/employees/${employeeId}/deactivate`, { method: "PATCH" });
}

export function resetEmployeePassword(employeeId: string) {
  return apiRequest<null>(`/employees/${employeeId}/reset-password`, { method: "POST" });
}

export function forceLogoutEmployee(employeeId: string) {
  return apiRequest<{ sessions_revoked: number }>(`/employees/${employeeId}/force-logout`, { method: "POST" });
}

export function getEmployeeSessions(employeeId: string) {
  return apiRequest<SessionSummary[]>(`/employees/${employeeId}/sessions`);
}

export function getEmployeeLoginHistory(employeeId: string) {
  return apiRequest<LoginHistoryEntry[]>(`/employees/${employeeId}/login-history`);
}

export function getEmployeeActivitySummary(employeeId: string) {
  return apiRequest<ActivitySummary>(`/employees/${employeeId}/activity-summary`);
}

export function getOwnProfile() {
  return apiRequest<EmployeeDetail>("/employees/me");
}

export function updateOwnProfile(payload: SelfUpdateEmployeeInput) {
  return apiRequest<EmployeeDetail>("/employees/me", { method: "PATCH", body: JSON.stringify(payload) });
}

export function getOwnLoginHistory() {
  return apiRequest<LoginHistoryEntry[]>("/employees/me/login-history");
}

export function getOwnPhotoUploadUrl() {
  return apiRequest<{ upload_url: string; s3_key: string }>("/employees/me/photo/upload-url", { method: "POST" });
}

export function confirmOwnPhoto(s3Key: string) {
  return apiRequest<EmployeeDetail>("/employees/me/photo", { method: "PATCH", body: JSON.stringify({ s3_key: s3Key }) });
}

export interface EmployeeDocument {
  id: string;
  document_type: string;
  file_name: string;
  s3_key: string;
  content_type: string | null;
  created_at: string;
}

export function getEmployeeDocuments(employeeId: string) {
  return apiRequest<EmployeeDocument[]>(`/employees/${employeeId}/documents`);
}

export function getEmployeeDocumentUploadUrl(employeeId: string, documentType: string, fileName: string, contentType?: string) {
  return apiRequest<{ upload_url: string; s3_key: string }>(`/employees/${employeeId}/documents/upload-url`, {
    method: "POST",
    body: JSON.stringify({ document_type: documentType, file_name: fileName, content_type: contentType }),
  });
}

export function confirmEmployeeDocument(employeeId: string, payload: { document_type: string; file_name: string; s3_key: string; content_type?: string }) {
  return apiRequest<EmployeeDocument>(`/employees/${employeeId}/documents`, { method: "POST", body: JSON.stringify(payload) });
}

export interface EmployeeDocumentOverviewItem extends EmployeeDocument {
  employee_id: string;
  employee_name: string;
}

export interface EmployeeActivityEntry {
  event_type: string;
  employee_id: string | null;
  employee_name: string | null;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface EmployeeDocumentsOverviewParams {
  page?: number;
  page_size?: number;
  employee_id?: string;
  document_type?: string;
}

export interface EmployeeActivityOverviewParams {
  page?: number;
  page_size?: number;
  employee_id?: string;
  event_type?: string;
  date_from?: string;
  date_to?: string;
}

function toGenericQuery<T extends object>(params: T): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, string | number | undefined>)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export async function listAllEmployeeDocuments(params: EmployeeDocumentsOverviewParams): Promise<PaginatedResponse<EmployeeDocumentOverviewItem>> {
  const envelope = await apiRequestRaw<EmployeeDocumentOverviewItem[]>(`/employees/documents${toGenericQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export async function listEmployeeActivity(params: EmployeeActivityOverviewParams): Promise<PaginatedResponse<EmployeeActivityEntry>> {
  const envelope = await apiRequestRaw<EmployeeActivityEntry[]>(`/employees/activity${toGenericQuery(params)}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function exportEmployeesCsvUrl(): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
  return `${base}/employees/export`;
}

export function listDepartments() {
  return apiRequest<MasterDataItem[]>("/departments");
}

export function listDesignations() {
  return apiRequest<MasterDataItem[]>("/designations");
}

export function listBranches() {
  return apiRequest<BranchItem[]>("/branches");
}
