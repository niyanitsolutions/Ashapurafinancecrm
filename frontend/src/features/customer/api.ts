import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";
import type { NamedMasterData } from "@/features/system_settings/api";

export interface Address {
  line1: string;
  line2?: string | null;
  city: string;
  state: string;
  pincode: string;
  country?: string;
}

export interface Customer {
  id: string;
  customer_code: string;
  full_name: string;
  mobile: string;
  email: string | null;
  date_of_birth: string | null;
  gender: string | null;
  pan_number_masked: string | null;
  aadhaar_number_masked: string | null;
  address: Address | null;
  status: string;
  converted_from_lead_id: string | null;
  created_at: string;
}

export interface CustomerListItem {
  id: string;
  customer_code: string;
  full_name: string;
  mobile: string;
  email: string | null;
  status: string;
  created_at: string;
}

export interface CompleteProfileInput {
  full_name: string;
  email?: string;
  date_of_birth?: string;
  gender?: string;
  pan_number?: string;
  aadhaar_number?: string;
  address?: Address;
}

export type UpdateProfileInput = Partial<CompleteProfileInput>;

// Phase 3.1 — conditional visibility: this field only counts/renders when the named
// controlling field's current value matches (mirrors backend field_validation.py).
export interface FieldCondition {
  field_key: string;
  operator: "equals" | "not_equals" | "in";
  value: unknown;
}

// Phase 3.1 — declarative validation metadata; `format` selects a built-in regex
// (kept in one place, `fieldValidation.ts`, mirroring the backend's own single source).
// Governance round — min_value/max_value/min_date/max_date/mask/auto_uppercase/trim.
export interface FieldValidation {
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  format?: "email" | "mobile" | "pan" | "aadhaar" | "ifsc" | "gst" | "pincode" | null;
  min_value?: number | null;
  max_value?: number | null;
  min_date?: string | null;
  max_date?: string | null;
  mask?: string | null;
  auto_uppercase?: boolean;
  trim?: boolean;
}

// Governance round — `source`/`master_key` trace a field back to its Master Template
// origin (see backend `app.features.customer.models` module docstring): a "master"
// field may be hidden/relabelled/reordered/re-validated by the Owner but never
// deleted/re-keyed/re-typed; a "custom" field (Owner-added) is fully free.
export type FieldSource = "master" | "custom";

export interface FormField {
  key: string;
  label: string;
  field_type: "text" | "number" | "date" | "select" | "textarea" | "checkbox";
  required: boolean;
  options: string[] | null;
  // Grouping label (e.g. "Basic Information") — null on older/ungrouped schemas, in
  // which case every field should render as one flat, unlabeled group.
  section: string | null;
  visible_when?: FieldCondition | null;
  validation?: FieldValidation | null;
  options_source?: "static" | "api";
  // Reserved for a future API-sourced dropdown (states/cities/branches) — no such
  // endpoint exists yet; the renderer already knows how to call one when it does.
  options_endpoint?: string | null;
  source?: FieldSource;
  master_key?: string | null;
  placeholder?: string | null;
  hidden?: boolean;
}

export interface RequiredDocument {
  document_type_id: string;
  document_type_name: string;
  section: string | null;
  note: string | null;
  name_override?: string | null;
  required?: boolean;
  allowed_types?: string[] | null;
  max_size_mb?: number | null;
  multiple_upload?: boolean;
  preview_enabled?: boolean;
  source?: FieldSource;
  hidden?: boolean;
}

// Phase 3.1 — a repeatable block of fields (Co-Applicants, Partners, Nominees, ...).
// Values live at `formData[group.key] = [{fieldKey: value, ...}, ...]`.
export interface RepeatableGroup {
  key: string;
  label: string;
  add_button_label: string | null;
  min_count: number;
  max_count: number | null;
  fields: FormField[];
}

export type SchemaStatus = "active" | "draft" | "archived";

export interface FormDefinition {
  id: string;
  product_category: string;
  product_id: string;
  product_name: string;
  fields: FormField[];
  required_documents: RequiredDocument[];
  repeatable_groups: RepeatableGroup[];
  // Schema version/audit metadata — Owner/Admin-only, never render this to a Customer.
  status: SchemaStatus;
  version: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  // Governance round — freeze/version lifecycle. `schema_version` is the Owner-facing
  // "Version 2"/"Version 3" — deliberately separate from `version` above (which bumps
  // on every write, including a plain Hide/relabel edit) so it only ever changes via
  // "New Version" and always means what it says.
  is_locked: boolean;
  frozen_at: string | null;
  frozen_by: string | null;
  schema_version: number;
  source_schema_version: number | null;
}

// ---- product schema authoring (Owner) ----
// `source`/`master_key` are deliberately absent from the *Input* shapes below — they're
// never client-supplied. The backend derives them itself by diffing incoming `key`s
// against the stored schema's current fields, which is what makes the master/custom
// split tamper-proof (see `CustomerService.update_form_definition`'s diff-by-key merge).

export interface FormFieldInput {
  key: string;
  label: string;
  field_type: FormField["field_type"];
  required?: boolean;
  options?: string[] | null;
  section?: string | null;
  visible_when?: FieldCondition | null;
  validation?: FieldValidation | null;
  options_source?: "static" | "api";
  options_endpoint?: string | null;
  placeholder?: string | null;
  hidden?: boolean;
}

export interface RequiredDocumentInput {
  document_type_id: string;
  section?: string | null;
  note?: string | null;
  name_override?: string | null;
  required?: boolean;
  allowed_types?: string[] | null;
  max_size_mb?: number | null;
  multiple_upload?: boolean;
  preview_enabled?: boolean;
  hidden?: boolean;
}

export interface RepeatableGroupInput {
  key: string;
  label: string;
  add_button_label?: string | null;
  min_count?: number;
  max_count?: number | null;
  fields: FormFieldInput[];
}

export interface FormDefinitionCreateInput {
  product_category: string;
  product_id: string;
  fields: FormFieldInput[];
  required_documents: RequiredDocumentInput[];
  repeatable_groups?: RepeatableGroupInput[];
  status?: SchemaStatus;
}

export interface FormDefinitionUpdateInput {
  fields?: FormFieldInput[];
  required_documents?: RequiredDocumentInput[];
  repeatable_groups?: RepeatableGroupInput[];
  status?: SchemaStatus;
}

export interface ApplicationListItem {
  id: string;
  application_code: string;
  customer_id: string | null;
  customer_name: string | null;
  lead_id: string | null;
  product_category: string;
  product_id: string;
  product_name: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  status: "draft" | "submitted";
  created_at: string;
  submitted_at: string | null;
  progress_percent: number;
}

export interface ApplicationDetail extends ApplicationListItem {
  form_definition_id: string;
  form_data: Record<string, unknown>;
  updated_at: string;
}

export interface ApplicationDocument {
  id: string;
  application_id: string;
  document_type_id: string;
  document_type_name: string;
  file_name: string;
  content_type: string | null;
  download_url: string | null;
  created_at: string;
  verification_status: "pending" | "verified" | "rejected";
  verified_by_name: string | null;
  verified_at: string | null;
  rejection_reason: string | null;
}

// `link_status` is the only field guaranteed to be present — every other field is
// populated only for the outcome it's relevant to (never `lead_id`/internal IDs).
export type LinkStatus = "valid" | "not_found" | "expired" | "disabled" | "already_used" | "already_submitted";

export interface ResolvedSecureLink {
  link_status: LinkStatus;
  full_name?: string;
  mobile?: string;
  email?: string;
  product_category?: string;
  product_id?: string;
  product_name?: string;
  has_active_account?: boolean;
  application_reference?: string;
  submitted_at?: string;
  application_status?: string;
  // Application Summary card (valid link only)
  lead_reference?: string;
  created_by_name?: string;
  link_created_at?: string;
  // Expired-link "Contact your Relationship Manager" card only
  relationship_manager_name?: string;
  relationship_manager_mobile?: string;
  relationship_manager_email?: string;
}

export interface SecureLink {
  id: string;
  secure_code: string;
  link_url: string;
  status: "active" | "used" | "revoked";
  expires_at: string;
  one_time_use: boolean;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  used_at: string | null;
  last_opened_at: string | null;
  notification_status: Record<string, string> | null;
}

export type NotifyChannel = "whatsapp" | "sms" | "email";

export interface GenerateSecureLinkInput {
  expiry_minutes?: number;
  one_time_use?: boolean;
  notify_channels?: NotifyChannel[];
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta | null;
}

// ---- public onboarding ----

export function startDirectRegistration(mobile: string) {
  // `bypass_available` is TEMPORARY — only true when the backend's MSG91 DLT-approval
  // testing bypass (Settings.registration_otp_bypass) is on. Never trust this alone to
  // mark a mobile verified — bypassVerifyMobile below re-checks the same flag on the
  // backend regardless of what this said.
  return apiRequest<{ dev_otp: string | null; bypass_available: boolean }>("/customer-registration/start", {
    method: "POST",
    body: JSON.stringify({ mobile }),
  });
}

// TEMPORARY — MSG91 DLT Sender ID/template approval testing bypass, customer
// self-registration only. Remove once DLT approval lands and
// Settings.registration_otp_bypass is retired on the backend.
export function bypassVerifyRegistrationMobile(mobile: string) {
  return apiRequest<{ otp_verified_token: string }>("/customer-registration/bypass-verify", {
    method: "POST",
    body: JSON.stringify({ mobile }),
  });
}

export interface CompleteDirectRegistrationInput {
  full_name: string;
  email: string;
  mobile: string;
  password: string;
  address_line1: string;
  city: string;
  state: string;
  pincode: string;
  otp_verified_token: string;
}

export function completeDirectRegistration(payload: CompleteDirectRegistrationInput) {
  return apiRequest<null>("/customer-registration/complete", { method: "POST", body: JSON.stringify(payload) });
}

export function resolveSecureLink(secureCode: string) {
  return apiRequest<ResolvedSecureLink>(`/secure-links/${secureCode}`);
}

// ---- secure link claim (authenticated customer) ----

export function claimSecureLink(secureCode: string) {
  return apiRequest<ApplicationDetail>(`/secure-links/${secureCode}/claim`, { method: "POST" });
}

// ---- secure link generation/management (staff) ----

export function getCurrentSecureLink(leadId: string) {
  return apiRequest<SecureLink | null>(`/leads/${leadId}/secure-link`);
}

export function generateSecureLink(leadId: string, input: GenerateSecureLinkInput = {}) {
  return apiRequest<SecureLink>(`/leads/${leadId}/secure-links`, { method: "POST", body: JSON.stringify(input) });
}

export function disableSecureLink(linkId: string) {
  return apiRequest<SecureLink>(`/secure-links/${linkId}/disable`, { method: "POST" });
}

export function notifySecureLink(linkId: string, channels: NotifyChannel[]) {
  return apiRequest<SecureLink>(`/secure-links/${linkId}/notify`, { method: "POST", body: JSON.stringify({ channels }) });
}

export function logSecureLinkEvent(linkId: string, eventType: string) {
  return apiRequest<null>(`/secure-links/${linkId}/log-event`, { method: "POST", body: JSON.stringify({ event_type: eventType }) });
}

// ---- customer profile (self) ----

export function getOwnCustomerProfile() {
  return apiRequest<Customer | null>("/customers/me");
}

export function completeOwnProfile(payload: CompleteProfileInput) {
  return apiRequest<Customer>("/customers/me", { method: "POST", body: JSON.stringify(payload) });
}

export function updateOwnProfile(payload: UpdateProfileInput) {
  return apiRequest<Customer>("/customers/me", { method: "PATCH", body: JSON.stringify(payload) });
}

// ---- form definitions (Product Schema Engine — shared read, every portal) ----

export function getFormDefinition(productCategory: string, productId: string) {
  return apiRequest<FormDefinition>(`/application-form-definitions?product_category=${productCategory}&product_id=${productId}`);
}

// ---- active products (Customer Portal's own read — never system_settings' employee-gated endpoints) ----

export function listPortalProducts(category: "loan" | "insurance") {
  return apiRequest<NamedMasterData[]>(`/portal-products?category=${category}`);
}

// ---- product schema authoring (Owner) ----

export function listProductSchemas() {
  return apiRequest<FormDefinition[]>("/product-schemas");
}

export function getProductSchema(formDefinitionId: string) {
  return apiRequest<FormDefinition>(`/product-schemas/${formDefinitionId}`);
}

export function createProductSchema(payload: FormDefinitionCreateInput) {
  return apiRequest<FormDefinition>("/product-schemas", { method: "POST", body: JSON.stringify(payload) });
}

export function updateProductSchema(formDefinitionId: string, payload: FormDefinitionUpdateInput) {
  return apiRequest<FormDefinition>(`/product-schemas/${formDefinitionId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

// ---- product schema governance (freeze/version/publish/compare/audit) ----

export function freezeProductSchema(formDefinitionId: string, confirmedChecklist: string[]) {
  return apiRequest<FormDefinition>(`/product-schemas/${formDefinitionId}/freeze`, {
    method: "POST",
    body: JSON.stringify({ confirmed_checklist: confirmedChecklist }),
  });
}

export function createProductSchemaVersion(formDefinitionId: string) {
  return apiRequest<FormDefinition>(`/product-schemas/${formDefinitionId}/new-version`, { method: "POST" });
}

export function publishProductSchema(formDefinitionId: string) {
  return apiRequest<FormDefinition>(`/product-schemas/${formDefinitionId}/publish`, { method: "POST" });
}

export interface SchemaFieldDiffEntry {
  key: string;
  attribute: string;
  old_value: unknown;
  new_value: unknown;
}

export interface SchemaCompareResponse {
  product_name: string;
  schema_version_a: number;
  schema_version_b: number;
  added_fields: FormField[];
  removed_fields: FormField[];
  modified_fields: SchemaFieldDiffEntry[];
  added_documents: RequiredDocument[];
  removed_documents: RequiredDocument[];
  modified_documents: SchemaFieldDiffEntry[];
  unchanged_field_count: number;
  unchanged_document_count: number;
}

export function compareProductSchemas(productCategory: string, productId: string, schemaVersionA: number, schemaVersionB: number) {
  const params = new URLSearchParams({
    product_category: productCategory,
    product_id: productId,
    schema_version_a: String(schemaVersionA),
    schema_version_b: String(schemaVersionB),
  });
  return apiRequest<SchemaCompareResponse>(`/product-schemas/compare?${params}`);
}

export interface SchemaAuditEntry {
  id: string;
  event_type: string;
  changed_by: string | null;
  changed_by_name: string | null;
  changed_at: string;
  changes: SchemaFieldDiffEntry[];
  metadata: Record<string, unknown>;
}

export function getProductSchemaAudit(productCategory: string, productId: string) {
  const params = new URLSearchParams({ product_category: productCategory, product_id: productId });
  return apiRequest<SchemaAuditEntry[]>(`/product-schemas/audit?${params}`);
}

// ---- applications (customer self-service) ----

export function startApplication(productCategory: string, productId: string) {
  return apiRequest<ApplicationDetail>("/applications", { method: "POST", body: JSON.stringify({ product_category: productCategory, product_id: productId }) });
}

export function listOwnApplications(status?: string) {
  const qs = status ? `?status=${status}` : "";
  return apiRequest<ApplicationListItem[]>(`/applications/me${qs}`);
}

export function getApplication(applicationId: string) {
  return apiRequest<ApplicationDetail>(`/applications/${applicationId}`);
}

export function updateApplication(applicationId: string, payload: { form_data?: Record<string, unknown>; pending_profile?: Record<string, unknown> }) {
  return apiRequest<ApplicationDetail>(`/applications/${applicationId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function submitApplication(applicationId: string, profile?: CompleteProfileInput) {
  return apiRequest<ApplicationDetail>(`/applications/${applicationId}/submit`, { method: "POST", body: JSON.stringify({ profile }) });
}

export function getDocumentUploadUrl(applicationId: string, documentTypeId: string, fileName: string, contentType?: string) {
  return apiRequest<{ upload_url: string; s3_key: string }>(`/applications/${applicationId}/documents/upload-url`, {
    method: "POST",
    body: JSON.stringify({ document_type_id: documentTypeId, file_name: fileName, content_type: contentType }),
  });
}

export function confirmDocument(applicationId: string, documentTypeId: string, fileName: string, s3Key: string, contentType?: string) {
  return apiRequest<ApplicationDocument>(`/applications/${applicationId}/documents`, {
    method: "POST",
    body: JSON.stringify({ document_type_id: documentTypeId, file_name: fileName, s3_key: s3Key, content_type: contentType }),
  });
}

export function listDocuments(applicationId: string) {
  return apiRequest<ApplicationDocument[]>(`/applications/${applicationId}/documents`);
}

// ---- document verification (staff) ----

export function verifyDocument(applicationId: string, documentId: string) {
  return apiRequest<ApplicationDocument>(`/applications/${applicationId}/documents/${documentId}/verify`, { method: "PATCH" });
}

export function rejectDocument(applicationId: string, documentId: string, reason: string) {
  return apiRequest<ApplicationDocument>(`/applications/${applicationId}/documents/${documentId}/reject`, {
    method: "PATCH",
    body: JSON.stringify({ reason }),
  });
}

// ---- Phase 5: Portal Home / Dashboard ----

export interface RelationshipManager {
  id: string;
  name: string;
  email: string;
  mobile: string;
}

export interface DocumentPreviewItem {
  document_type_id: string;
  document_type_name: string;
  note: string | null;
  uploaded: boolean;
}

export interface DocumentGroupPreview {
  section: string | null;
  documents: DocumentPreviewItem[];
}

export interface PortalDashboard {
  has_application: boolean;
  has_lead: boolean;
  application_id: string | null;
  application_code: string | null;
  product_name: string | null;
  product_category: string | null;
  status_label: string | null;
  current_stage_label: string | null;
  progress_percent: number;
  next_action: string | null;
  relationship_manager: RelationshipManager | null;
  pending_documents_count: number;
  completed_documents_count: number;
  document_groups: DocumentGroupPreview[];
  recent_message_count: number;
  recent_messages: MessageItem[];
  recent_activity: { event_type: string; created_at: string | null }[];
}

export interface TimelineEntry {
  label: string;
  state: "completed" | "current" | "upcoming" | "rejected";
  occurred_at: string | null;
  actor_name: string | null;
}

export interface MessageItem {
  channel: string;
  template_name: string;
  subject: string | null;
  body: string;
  status: string;
  sent_at: string | null;
  created_at: string;
}

export function getOwnDashboard() {
  return apiRequest<PortalDashboard>("/customers/me/dashboard");
}

export function getApplicationTimeline(applicationId: string) {
  return apiRequest<TimelineEntry[]>(`/applications/${applicationId}/timeline`);
}

export function listOwnMessages() {
  return apiRequest<MessageItem[]>("/customers/me/messages");
}

export function raiseSupportRequest(subject: string, message: string) {
  return apiRequest<{ created_task: boolean }>("/customers/me/support-requests", {
    method: "POST",
    body: JSON.stringify({ subject, message }),
  });
}

// ---- staff views (Owner + assigned Employee) ----

export async function listApplicationsStaff(params: {
  page?: number; page_size?: number; search?: string; customer_id?: string; assigned_to?: string; unassigned_only?: boolean;
  status?: string; product_category?: string;
}): Promise<PaginatedResponse<ApplicationListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<ApplicationListItem[]>(`/applications${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function assignApplication(applicationId: string, employeeId: string) {
  return apiRequest<ApplicationDetail>(`/applications/${applicationId}/assign`, { method: "POST", body: JSON.stringify({ employee_id: employeeId }) });
}

export async function listCustomersStaff(params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<CustomerListItem>> {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  const envelope = await apiRequestRaw<CustomerListItem[]>(`/customers${qs ? `?${qs}` : ""}`);
  return { data: envelope.data ?? [], pagination: envelope.meta?.pagination ?? null };
}

export function getCustomerStaff(customerId: string) {
  return apiRequest<Customer>(`/customers/${customerId}`);
}
