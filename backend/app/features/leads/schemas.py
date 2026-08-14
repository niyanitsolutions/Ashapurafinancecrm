from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.features.leads.constants import ProductCategory


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


class AssignLeadRequest(BaseModel):
    employee_id: str


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
