from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.features.customer.constants import ConditionOperator, FieldFormat, FieldType, OptionsSource
from app.features.employee.schemas import AddressSchema
from app.security.password import PasswordStr

# ---------------------------------------------------------------------- onboarding (public)
# Authentication/registration itself always happens through Auth's own, single flow
# (POST /auth/login, /auth/send-otp+/auth/verify-otp+/auth/reset-password, wrapped by
# CustomerService.complete_direct_registration below for the Customer-only self-signup
# case) — nothing here duplicates that. A Secure Application Link only ever resolves its
# own status (below) and, once the customer is authenticated, gets claimed via the
# authenticated `claim_secure_link` endpoint in router.py.


class DirectRegisterRequest(BaseModel):
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")


class CompleteDirectRegistrationRequest(BaseModel):
    """Production Customer self-registration — the *only* self-registration path in the
    system (Owner/Employee/Referral Partner are always staff-created, decision 011/053).
    `otp_verified_token` (from `POST /auth/verify-otp`, after `start_direct_registration`
    sends the code) proves phone ownership; a real password is always required on top of
    that, never in place of it."""

    full_name: str = Field(min_length=3)
    email: EmailStr
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    password: PasswordStr
    address_line1: str
    city: str
    state: str
    pincode: str = Field(pattern=r"^\d{6}$")
    otp_verified_token: str


class OtpKickoffResponse(BaseModel):
    dev_otp: str | None = None
    # TEMPORARY — true only when Settings.registration_otp_bypass is on (see
    # CustomerService.start_direct_registration / bypass_verify_registration_mobile).
    # Tells the frontend whether to offer the "Verify Mobile" bypass button instead of the
    # normal OTP-entry step; the frontend is never trusted to decide this on its own, and
    # the bypass-verify endpoint re-checks the same flag server-side regardless of what
    # this flag said.
    bypass_available: bool = False


class BypassVerifyMobileResponse(BaseModel):
    otp_verified_token: str


class ResolveSecureLinkResponse(BaseModel):
    """Never carries `lead_id`/Mongo IDs — only `link_status` is guaranteed; every other
    field is populated only for the outcome it's relevant to (see
    CustomerService.get_secure_link_public_status)."""

    link_status: str
    full_name: str | None = None
    mobile: str | None = None
    email: str | None = None
    product_category: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    has_active_account: bool | None = None
    application_reference: str | None = None
    submitted_at: datetime | None = None
    application_status: str | None = None
    # Application Summary card (valid link only) — see docs/decisions/DECISIONS.md.
    lead_reference: str | None = None
    created_by_name: str | None = None
    link_created_at: datetime | None = None
    # Expired-link "Contact your Relationship Manager" card only.
    relationship_manager_name: str | None = None
    relationship_manager_mobile: str | None = None
    relationship_manager_email: str | None = None


class GenerateSecureLinkRequest(BaseModel):
    expiry_minutes: int | None = None
    one_time_use: bool = True
    notify_channels: list[str] | None = None


class NotifySecureLinkRequest(BaseModel):
    channels: list[str]


class LogSecureLinkEventRequest(BaseModel):
    event_type: str = Field(pattern=r"^[a-z_]+$")


class SecureLinkResponse(BaseModel):
    """Staff-facing (Lead Details card) — `secure_code` is the opaque public
    identifier, never a JWT or a Mongo ID; `link_url` is the ready-to-share URL."""

    id: str
    secure_code: str
    link_url: str
    status: str
    expires_at: datetime
    one_time_use: bool
    created_by: str | None
    created_by_name: str | None
    created_at: datetime
    used_at: datetime | None
    last_opened_at: datetime | None
    notification_status: dict[str, str] | None


# ---------------------------------------------------------------------- customer profile


class CompleteProfileRequest(BaseModel):
    full_name: str
    email: EmailStr | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    pan_number: str | None = Field(default=None, min_length=4, max_length=20)
    aadhaar_number: str | None = Field(default=None, min_length=4, max_length=20)
    address: AddressSchema | None = None


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    pan_number: str | None = Field(default=None, min_length=4, max_length=20)
    aadhaar_number: str | None = Field(default=None, min_length=4, max_length=20)
    address: AddressSchema | None = None


class CustomerResponse(BaseModel):
    id: str
    customer_code: str
    full_name: str
    mobile: str
    email: str | None
    date_of_birth: date | None
    gender: str | None
    pan_number_masked: str | None
    aadhaar_number_masked: str | None
    address: AddressSchema | None
    status: str
    converted_from_lead_id: str | None
    # "lead" | "direct" — derived purely from `converted_from_lead_id is not None`, never
    # guessed from product/employee/referral/status. See `Customer.converted_from_lead_id`.
    registration_source: str
    lead_code: str | None = None
    lead_source_name: str | None = None
    created_at: datetime


class CustomerListItem(BaseModel):
    id: str
    customer_code: str
    full_name: str
    mobile: str
    email: str | None
    status: str
    registration_source: str
    created_at: datetime


# ---------------------------------------------------------------------- form definitions


class FieldConditionResponse(BaseModel):
    field_key: str
    operator: str
    value: Any


class FieldValidationResponse(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    mask: str | None = None
    auto_uppercase: bool = False
    trim: bool = False


class FormFieldResponse(BaseModel):
    key: str
    label: str
    field_type: str
    required: bool
    options: list[str] | None
    section: str | None = None
    visible_when: FieldConditionResponse | None = None
    validation: FieldValidationResponse | None = None
    options_source: str = "static"
    options_endpoint: str | None = None
    source: str = "custom"
    master_key: str | None = None
    placeholder: str | None = None
    hidden: bool = False


class RequiredDocumentResponse(BaseModel):
    document_type_id: str
    document_type_name: str
    section: str | None = None
    note: str | None = None
    name_override: str | None = None
    required: bool = True
    allowed_types: list[str] | None = None
    max_size_mb: int | None = None
    multiple_upload: bool = False
    preview_enabled: bool = True
    source: str = "custom"
    hidden: bool = False
    # Bank Statement password support — inherited from this document type's own
    # DocumentType.supports_password master-data flag (see that field's docstring),
    # never set per-schema. Drives the optional password field the upload UI shows for
    # this required document, for every product whose schema references this type.
    supports_password: bool = False


class RepeatableGroupResponse(BaseModel):
    key: str
    label: str
    add_button_label: str | None = None
    min_count: int = 0
    max_count: int | None = None
    fields: list[FormFieldResponse]


class FormDefinitionResponse(BaseModel):
    id: str
    product_category: str
    product_id: str
    product_name: str = ""
    fields: list[FormFieldResponse]
    required_documents: list[RequiredDocumentResponse]
    repeatable_groups: list[RepeatableGroupResponse] = Field(default_factory=list)
    # Schema versioning (BaseDocument's own fields, surfaced here) — `version` auto-
    # increments on every update, so this is the schema's revision history without a
    # separate model. Owner/Admin-only in the frontend; never rendered to a Customer.
    status: str
    version: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    # Governance round — freeze/version lifecycle (see ApplicationFormDefinition).
    is_locked: bool = False
    frozen_at: datetime | None = None
    frozen_by: str | None = None
    schema_version: int = 1
    source_schema_version: int | None = None


# ------------------------------------------------------- form definitions (Owner authoring)
# The Product Schema Engine's authoring surface — Owner-only (see docs/roadmap
# `product_schema` permission). A field/document list here is a full replace on update,
# matching the "Owner edits the whole form, saves" UX rather than a field-by-field PATCH.


class FieldConditionInput(BaseModel):
    field_key: str
    operator: str = Field(default=ConditionOperator.EQUALS, pattern=f"^({'|'.join(ConditionOperator.ALL)})$")
    value: Any


class FieldValidationInput(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = Field(default=None, pattern=f"^({'|'.join(FieldFormat.ALL)})$")
    min_value: float | None = None
    max_value: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    mask: str | None = None
    auto_uppercase: bool = False
    trim: bool = False


class FormFieldInput(BaseModel):
    # `source`/`master_key` are deliberately NOT accepted here — they're never client-
    # supplied. `update_form_definition` derives them itself by diffing incoming `key`s
    # against the stored definition's current fields (see service.py), which is what
    # makes the master/custom split tamper-proof rather than a payload the Owner could
    # just set to bypass the permission model.
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    field_type: str = Field(pattern=f"^({'|'.join(FieldType.ALL)})$")
    required: bool = True
    options: list[str] | None = None
    section: str | None = None
    visible_when: FieldConditionInput | None = None
    validation: FieldValidationInput | None = None
    options_source: str = Field(default=OptionsSource.STATIC, pattern=f"^({'|'.join(OptionsSource.ALL)})$")
    options_endpoint: str | None = None
    placeholder: str | None = None
    hidden: bool = False


class RequiredDocumentInput(BaseModel):
    document_type_id: str
    section: str | None = None
    note: str | None = None
    name_override: str | None = None
    required: bool = True
    allowed_types: list[str] | None = None
    max_size_mb: int | None = None
    multiple_upload: bool = False
    preview_enabled: bool = True
    hidden: bool = False


class RepeatableGroupInput(BaseModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    add_button_label: str | None = None
    min_count: int = 0
    max_count: int | None = None
    fields: list[FormFieldInput] = Field(default_factory=list)


class FormDefinitionCreateRequest(BaseModel):
    product_category: str
    product_id: str
    fields: list[FormFieldInput] = Field(default_factory=list)
    required_documents: list[RequiredDocumentInput] = Field(default_factory=list)
    repeatable_groups: list[RepeatableGroupInput] = Field(default_factory=list)
    status: str = "draft"  # validated against SchemaStatus.ALL in the service layer


class FormDefinitionUpdateRequest(BaseModel):
    fields: list[FormFieldInput] | None = None
    required_documents: list[RequiredDocumentInput] | None = None
    repeatable_groups: list[RepeatableGroupInput] | None = None
    status: str | None = None  # validated against SchemaStatus.ALL in the service layer


class FreezeFormDefinitionRequest(BaseModel):
    """Ask #10 — the frontend's 14-item Freeze Checklist is a client-side gate on when
    this endpoint is even called; `confirmed_checklist` is carried through into the
    freeze's audit-log entry purely for traceability (ask #9), not re-validated here."""

    confirmed_checklist: list[str] = Field(default_factory=list)


class SchemaFieldDiffEntry(BaseModel):
    key: str
    attribute: str
    old_value: Any = None
    new_value: Any = None


class SchemaCompareResponse(BaseModel):
    product_name: str = ""
    schema_version_a: int
    schema_version_b: int
    added_fields: list[FormFieldResponse] = Field(default_factory=list)
    removed_fields: list[FormFieldResponse] = Field(default_factory=list)
    modified_fields: list[SchemaFieldDiffEntry] = Field(default_factory=list)
    added_documents: list[RequiredDocumentResponse] = Field(default_factory=list)
    removed_documents: list[RequiredDocumentResponse] = Field(default_factory=list)
    modified_documents: list[SchemaFieldDiffEntry] = Field(default_factory=list)
    unchanged_field_count: int = 0
    unchanged_document_count: int = 0


class SchemaAuditEntryResponse(BaseModel):
    id: str
    event_type: str
    changed_by: str | None
    changed_by_name: str | None
    changed_at: datetime
    changes: list[SchemaFieldDiffEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------- applications


class StartApplicationRequest(BaseModel):
    product_category: str
    product_id: str


class UpdateApplicationRequest(BaseModel):
    form_data: dict[str, Any] | None = None
    pending_profile: dict[str, Any] | None = None


class SubmitApplicationRequest(BaseModel):
    profile: CompleteProfileRequest | None = None


class AssignApplicationRequest(BaseModel):
    employee_id: str


class ApplicationListItem(BaseModel):
    id: str
    application_code: str
    customer_id: str | None
    customer_name: str | None
    lead_id: str | None
    product_category: str
    product_id: str
    product_name: str
    assigned_to: str | None
    assigned_to_name: str | None
    status: str
    created_at: datetime
    submitted_at: datetime | None
    # Phase 3.1 — % of the schema's currently-visible required fields (Basic Information
    # + any repeatable-group blocks already added) that have a value right now. Purely a
    # progress *indicator* for the Customer Portal — never gates Save/Submit itself.
    # Originally Detail-only; the Customer Portal redesign's My Applications card layout
    # needs it on the list too, computed the same way (see `compute_progress_for_application`).
    progress_percent: int = 0
    # Assignment/status consistency — the linked Loan/Insurance Case, if one exists yet.
    # `assigned_to`/`assigned_to_name` above are already kept in sync with the case's own
    # (see `CustomerService.assign_application`/`LoanCaseService.assign_case`); these are
    # purely additive so a caller can also show the case's own pipeline status (which is
    # intentionally NOT the same thing as `status` above — see `ApplicationWorkflow.
    # current_status` vs `Application.status`). All default `None` — every existing
    # caller of `application_to_list_item`/`application_to_detail` keeps working
    # unmodified unless it opts in to resolving case info.
    case_id: str | None = None
    case_type: str | None = None
    case_code: str | None = None
    case_status: str | None = None
    case_status_label: str | None = None


class ApplicationDetailResponse(ApplicationListItem):
    form_definition_id: str
    form_data: dict[str, Any]
    updated_at: datetime


# ---------------------------------------------------------------------- documents


class DocumentUploadUrlRequest(BaseModel):
    document_type_id: str
    file_name: str
    content_type: str | None = None


class DocumentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmDocumentRequest(BaseModel):
    document_type_id: str
    file_name: str
    # Accepted for backward compatibility with existing frontend callers, but never
    # trusted — CustomerService.confirm_document re-derives the real S3 key server-side
    # instead of persisting whatever a client sends here (see that method's docstring).
    s3_key: str
    content_type: str | None = None
    # Bank Statement password — OPTIONAL, only meaningful when this document_type's own
    # DocumentType.supports_password is True (silently ignored otherwise — see
    # CustomerService.confirm_document). Never logged: RequestLoggingMiddleware only
    # ever logs method/path/status/duration, never a request body. Encrypted at rest
    # immediately, never persisted as plaintext; never echoed back in any response.
    password: str | None = Field(default=None, max_length=256)


class ApplicationDocumentResponse(BaseModel):
    id: str
    application_id: str
    document_type_id: str
    document_type_name: str
    file_name: str | None
    content_type: str | None
    download_url: str | None
    created_at: datetime
    verification_status: str
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    document_status: str = "uploaded"
    file_size_bytes: int | None = None
    is_current: bool = True
    doc_version: int = 1
    replaces_document_id: str | None = None
    # Boolean only — the plaintext/ciphertext password is NEVER included in this (or
    # any list) response. An authorized staff member retrieves the actual value only via
    # the dedicated GET .../password endpoint, gated the same as Verify/Reject.
    has_password: bool = False


class RejectDocumentRequest(BaseModel):
    reason: str = Field(min_length=1)


class DocumentPasswordResponse(BaseModel):
    """Response for the dedicated, staff-only reveal endpoint — deliberately its own
    narrow schema, never merged into ApplicationDocumentResponse, so the plaintext
    password can never accidentally ride along on a list/get call."""

    password: str


# ---------------------------------------------------------------------- Phase 5: Portal Home / Dashboard


class RelationshipManagerResponse(BaseModel):
    id: str
    name: str
    email: str
    mobile: str


class DocumentPreviewItem(BaseModel):
    document_type_id: str
    document_type_name: str
    note: str | None = None
    uploaded: bool


class DocumentGroupPreview(BaseModel):
    section: str | None
    documents: list[DocumentPreviewItem]


class PortalDashboardResponse(BaseModel):
    """One summary call for the Customer Portal's landing page (performance
    requirement — avoid several round-trips just to render the home screen). Detail
    views (full timeline, full document list, full message history) are separate,
    lazily-fetched endpoints, called only once the customer opens that screen."""

    has_application: bool
    has_lead: bool = False  # whether this application originated from a Lead (Flow 1)
    application_id: str | None = None
    application_code: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    # "Draft" | "Submitted" | "Under Review" | "Approved" | "Rejected" — Draft/Submitted
    # come straight from `Application.status`; the richer buckets are derived from the
    # matching Loan/Insurance case's `current_status` once one exists (see Phase 5 report
    # for the exact status->bucket mapping — never a new, parallel status field).
    status_label: str | None = None
    current_stage_label: str | None = None
    progress_percent: int = 0
    next_action: str | None = None
    relationship_manager: RelationshipManagerResponse | None = None
    pending_documents_count: int = 0
    completed_documents_count: int = 0
    # Phase 5.1 — the grouped preview the Home dashboard's Pending Documents card
    # renders directly (read-only; uploading still happens on the Document Center /
    # Application page, not inline here) — same grouping/section data as
    # `FormDefinitionResponse.required_documents`, just paired with upload status.
    document_groups: list[DocumentGroupPreview] = Field(default_factory=list)
    # CommunicationHistory has no read/unread tracking (that's specific to the internal
    # Notification model — see Phase 5 report) — this is a plain recent-activity count,
    # not a fabricated "unread" figure.
    recent_message_count: int = 0
    recent_messages: list["MessageItem"] = Field(default_factory=list)
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)


class TimelineEntryResponse(BaseModel):
    label: str
    state: str  # "completed" | "current" | "upcoming" | "rejected"
    occurred_at: datetime | None = None
    actor_name: str | None = None


class MessageItem(BaseModel):
    channel: str
    template_name: str
    subject: str | None
    body: str
    status: str
    sent_at: datetime | None
    created_at: datetime


class RaiseSupportRequestRequest(BaseModel):
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)


class SupportRequestResponse(BaseModel):
    created_task: bool
    # False when there was no assigned Relationship Manager yet — an Owner was notified
    # instead (see CustomerService.raise_support_request).
