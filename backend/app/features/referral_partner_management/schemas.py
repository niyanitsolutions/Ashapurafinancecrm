from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.security.password import PasswordStr


class CreateReferralPartnerRequest(BaseModel):
    initial_password: PasswordStr | None = Field(default=None, repr=False)
    confirm_password: str | None = Field(default=None, repr=False)
    reuse_existing_identity: bool = False
    temporary_password: bool = False
    request_id: str = Field(min_length=16, max_length=100)

    @model_validator(mode="after")
    def matching_passwords(self) -> "CreateReferralPartnerRequest":
        if self.reuse_existing_identity:
            if self.initial_password or self.confirm_password:
                raise ValueError("Do not provide passwords when associating an existing identity.")
        elif not self.initial_password or self.initial_password != self.confirm_password:
            raise ValueError("Matching initial and confirmation passwords are required.")
        if self.initial_password and len(self.initial_password.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes.")
        self.full_name = self.full_name.strip()
        if not self.full_name:
            raise ValueError("Full name is required.")
        return self

    full_name: str = Field(min_length=1, max_length=150)
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    business_name: str | None = None


class ReferralPartnerResponse(BaseModel):
    kyc_status: str = "pending"
    account_active: bool = True
    submission_mode: str = "partner_review"
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
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    fixed_event_policy: str | None = None
    product_id: str | None = None
    effective_from: datetime
    effective_until: datetime | None = None
    terms: str = ""
    fixed_contract_confirmed: bool = False
    label: str
    product_category: str | None = None
    partner_id: str | None = None
    calculation_type: str
    rate_or_amount: float
    trigger_event: str


class UpdateCommissionRuleRequest(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(active|inactive)$")

    @model_validator(mode="after")
    def preserve_required_values(self) -> "UpdateCommissionRuleRequest":
        for key in {"label", "calculation_type", "rate_or_amount", "trigger_event", "status", "fixed_contract_confirmed"} & self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be cleared.")
        if "terms" in self.model_fields_set and self.terms is None:
            self.terms = ""
        return self
    fixed_event_policy: str | None = None
    product_id: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    terms: str | None = None
    fixed_contract_confirmed: bool | None = None
    label: str | None = None
    product_category: str | None = None
    partner_id: str | None = None
    calculation_type: str | None = None
    rate_or_amount: float | None = None
    trigger_event: str | None = None


class CommissionRuleResponse(BaseModel):
    previous_rule_id: str | None = None
    fixed_contract_confirmed: bool = False
    fixed_event_policy: str | None = None
    product_id: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    rule_version: int = 1
    terms: str = ""
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
    approved_amount: float | None = None
    reserved_amount: float = 0
    additional_earned_amount: float = 0
    total_earned_amount: float = 0
    disbursement_event_source: str = "application_status_history"
    version: int = 1
    adjusted_amount: float = 0
    recovery_due_amount: float = 0
    application_id: str | None = None
    disbursement_event_id: str | None = None
    paid_amount: float = 0
    outstanding_amount: float | None = None
    rule_version: int = 1
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
