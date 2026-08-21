from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.features.leads.constants import LeadStage, ProductCategory
from app.features.leads.models import LeadFinancialAssessment
from app.security.password import PasswordStr


class CreateLeadRequest(BaseModel):
    full_name: str
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    source_id: str
    product_category: str = Field(pattern=f"^({'|'.join(ProductCategory.ALL)})$")
    product_id: str
    remarks: str | None = None
    city: str | None = None
    preferred_amount: float | None = Field(default=None, gt=0)
    salary_in_hand: float | None = Field(default=None, gt=0)
    next_follow_up_date: date | None = None
    # Seeds the lead's first Comment History entry (LeadNote) if provided — omitting it
    # behaves exactly as before this field existed.
    comment: str | None = None
    # Employee id, or repository.py's SELF_SENTINEL for "assign to me" — omitting it
    # leaves the lead unassigned (stage stays "fresh"), same as before this field existed.
    assigned_to: str | None = None
    # Optional — populated only when the selected product has a Product Schema and the
    # caller (Employee/Referral Partner Create Lead) rendered its Basic Information
    # fields. Omitting it entirely behaves exactly as before this field existed.
    product_form_data: dict[str, Any] | None = None
    # Optional — the caller's current coordinates (browser geolocation), only checked
    # against an active Geo Fence when one is configured for lead_creation; omitting
    # these behaves exactly as before this field existed, unless a Geo Fence for this
    # activity requires them (see app/features/geo_fencing/enforcement.py).
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class UpdateLeadRequest(BaseModel):
    full_name: str | None = None
    mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    source_id: str | None = None
    product_category: str | None = Field(default=None, pattern=f"^({'|'.join(ProductCategory.ALL)})$")
    product_id: str | None = None
    remarks: str | None = None
    city: str | None = None
    preferred_amount: float | None = Field(default=None, gt=0)
    salary_in_hand: float | None = Field(default=None, gt=0)
    next_follow_up_date: date | None = None
    # Every edit-time comment becomes a NEW LeadNote — never overwrites a prior one (see
    # docs/decisions/DECISIONS.md #125).
    comment: str | None = None
    # Employee id, or SELF_SENTINEL — reassigns the lead via the same path Create Lead
    # and POST /leads/{id}/assign use. Omitting it leaves the current assignment as-is.
    assigned_to: str | None = None


class AssignLeadRequest(BaseModel):
    employee_id: str


class RejectLeadRequest(BaseModel):
    reason: str = Field(min_length=1)


class SetStageRequest(BaseModel):
    stage: str = Field(pattern=f"^({LeadStage.ASSIGNED}|{LeadStage.DOCUMENT_COLLECTION}|{LeadStage.LOAN_MANAGEMENT})$")


class FollowUpRequest(BaseModel):
    next_follow_up_date: date
    comment: str | None = None


class FinancialAssessmentRequest(BaseModel):
    """My Leads' Update screen (spec section 13, Phase 2 / decision 125). Every field
    optional — a missing field is left at its previous value is NOT the semantics here;
    this is a whole-object replace (see LeadService.set_financial_assessment), so the
    frontend always submits its full current form state, not a sparse patch."""

    mock_off_salary: float | None = Field(default=None, ge=0)
    salary_mode: str | None = None
    emi_range: str | None = None
    total_experience: str | None = None
    current_company_experience: str | None = None
    company_location: str | None = None
    any_loan: bool | None = None
    last_3_months_salary: str | None = None
    cibil_score: int | None = Field(default=None, ge=300, le=900)
    cibil_unknown: bool = False
    remarks: str | None = None


class CreateCustomerAccountRequest(BaseModel):
    """No `phone_number` field on purpose — the account's mobile is always the Lead's
    own `mobile`, enforced server-side (see CustomerService.create_staff_initiated_account),
    so a staff-typed mobile can never diverge from the Lead it was created for."""

    password: PasswordStr


class AddNoteRequest(BaseModel):
    text: str = Field(min_length=1)


class LeadListItem(BaseModel):
    id: str
    lead_code: str
    full_name: str
    mobile: str
    email: str | None
    source_id: str
    source_name: str
    product_category: str
    product_id: str
    product_name: str
    assigned_to: str | None
    assigned_to_name: str | None
    status: str
    stage: str
    salary_in_hand: float | None
    next_follow_up_date: datetime | None
    assigned_by: str | None
    assigned_by_name: str | None
    assigned_at: datetime | None
    rejected_reason: str | None
    rejected_by: str | None
    rejected_by_name: str | None
    rejected_at: datetime | None
    # Leads workflow redesign Phase 3 (decision 126) — read-only enrichment from the
    # existing Application entity (Module 6B), populated only for Document Collection
    # tab list responses (see LeadService.list_leads); null for every other tab/lead.
    application_id: str | None = None
    application_status: str | None = None  # "draft" | "submitted" | None (no Application yet)
    is_potential_duplicate: bool
    created_at: datetime


class LeadDetailResponse(LeadListItem):
    remarks: str | None
    city: str | None
    preferred_amount: float | None
    duplicate_of_lead_ids: list[str]
    updated_at: datetime
    form_definition_id: str | None = None
    product_form_data: dict[str, Any] | None = None
    # Phase 2 (decision 125) — only on the detail response, not the list, keeping
    # Phase 1's list payload unchanged.
    financial_assessment: LeadFinancialAssessment | None = None
    account_created: bool = False
    # Phase 3 (decision 126) — document-completion summary against the linked
    # Application's required documents; zeros/false when no Application exists yet.
    documents_required: int = 0
    documents_verified: int = 0
    all_documents_verified: bool = False


class LeadCountsResponse(BaseModel):
    fresh: int
    my_leads: int
    document_collection: int
    rejected: int
    assigned: int


class NoteResponse(BaseModel):
    id: str
    lead_id: str
    text: str
    created_by: str | None
    created_at: datetime


class TimelineEntryResponse(BaseModel):
    type: str  # "activity" | "note"
    event_type: str | None = None
    text: str | None = None
    metadata: dict[str, Any] | None = None
    created_by: str | None
    created_at: datetime


class DuplicateCheckResponse(BaseModel):
    matches: list[LeadListItem]


class LookupItem(BaseModel):
    id: str
    name: str


class LeadLookupResponse(BaseModel):
    """Backs the Create Lead form's Source/Product dropdowns — see
    LeadService.get_lookup_data for why this is a Leads-owned read (gated on
    `leads:leads:view`) rather than proxying `system_settings`'s own CRUD-gated
    lead-sources/loan-products/insurance-products endpoints."""

    sources: list[LookupItem]
    loan_products: list[LookupItem]
    insurance_products: list[LookupItem]


class EligibleAssigneeResponse(BaseModel):
    """A candidate for Lead assignment — active employees who have module access
    matching the lead's product category (see LeadService.list_eligible_assignees /
    PRODUCT_CATEGORY_MODULE), enriched with business context (designation/branch/
    current workload/product specialization) purely for the Owner/Employee's benefit.
    Never a new authorization concept — see docs/decisions/DECISIONS.md.
    """

    id: str
    display_name: str
    designation_name: str
    branch_name: str
    current_lead_count: int
    product_match: bool
    recommended: bool
