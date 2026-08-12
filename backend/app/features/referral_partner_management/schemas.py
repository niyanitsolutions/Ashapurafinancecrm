from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CreateReferralPartnerRequest(BaseModel):
    full_name: str
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    business_name: str | None = None


class ReferralPartnerResponse(BaseModel):
    id: str
    partner_code: str
    full_name: str
    mobile: str
    email: str | None
    business_name: str | None
    approval_status: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AddReferralLeadRequest(BaseModel):
    full_name: str
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    product_category: str
    product_id: str
    remarks: str | None = None
    # Optional — same Product Schema Engine field as Employee Create Lead
    # (`leads.CreateLeadRequest.product_form_data`); omitting it behaves exactly as before.
    product_form_data: dict[str, Any] | None = None


class UpdateReferralLeadRequest(BaseModel):
    """Only the fields a Referral Partner is allowed to touch — never `source_id`/
    `product_category`/`product_id` (changing the product type of an already-submitted
    lead is out of scope). Rejected by the service once the lead's processing has
    started (docs/decisions/DECISIONS.md), regardless of which of these fields are set."""

    full_name: str | None = None
    mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    remarks: str | None = None


class ReferralLeadResponse(BaseModel):
    lead_id: str
    lead_code: str
    full_name: str
    mobile: str
    product_category: str
    product_id: str
    external_status: str
    editable: bool
    submitted_at: datetime


class CreateCommissionRuleRequest(BaseModel):
    label: str
    product_category: str | None = None
    partner_id: str | None = None
    calculation_type: str
    rate_or_amount: float
    trigger_event: str


class UpdateCommissionRuleRequest(BaseModel):
    label: str | None = None
    product_category: str | None = None
    partner_id: str | None = None
    calculation_type: str | None = None
    rate_or_amount: float | None = None
    trigger_event: str | None = None


class CommissionRuleResponse(BaseModel):
    id: str
    label: str
    product_category: str | None
    partner_id: str | None
    calculation_type: str
    rate_or_amount: float
    trigger_event: str
    status: str
    created_at: datetime
    updated_at: datetime


class CommissionEntryResponse(BaseModel):
    id: str
    partner_id: str
    partner_name: str | None
    lead_id: str
    case_type: str
    case_id: str
    rule_id: str
    calculation_type: str
    rate_or_amount: float
    base_amount: float
    commission_amount: float
    status: str
    approved_at: datetime | None
    paid_at: datetime | None
    payment_reference: str | None
    created_at: datetime


class SettleCommissionEntryRequest(BaseModel):
    payment_reference: str


class ReferralDashboardResponse(BaseModel):
    total_leads: int
    approved_leads: int
    rejected_leads: int
    commission_pending: float
    commission_approved: float
    commission_paid: float
    commission_balance: float
    recent_leads: list[ReferralLeadResponse]
