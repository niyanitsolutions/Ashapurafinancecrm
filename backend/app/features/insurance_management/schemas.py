from datetime import date, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.features.customer.schemas import ApplicationDocumentResponse
from app.features.insurance_management.constants import InsuranceHoldReason
from app.features.workflow_engine.constants import InsuranceStatus, ReEligibilityPeriod

# Stages an Insurance case can be created in directly from the manual "Add Insurance
# Lead" form. Policy Login / Policy Issued are deliberately excluded — a brand-new lead
# has no verified documents / premium, so those stages are only reachable via "Move To".
_MANUAL_CREATE_STAGES = (
    InsuranceStatus.FRESH_LEAD,
    InsuranceStatus.POLICY_DOCUMENT,
    InsuranceStatus.RE_ELIGIBLE,
    InsuranceStatus.REJECTED,
)
# Every stage "Move To" can target — anything except On Hold (its own Hold/Resume action).
_MOVE_TO_STAGES = tuple(s for s in InsuranceStatus.ALL if s != InsuranceStatus.ON_HOLD)

_INSURANCE_RE_ELIGIBILITY_OPTIONS = (
    ReEligibilityPeriod.THREE_MONTHS,
    ReEligibilityPeriod.SIX_MONTHS,
    ReEligibilityPeriod.TWELVE_MONTHS,
    ReEligibilityPeriod.CUSTOM,
    ReEligibilityPeriod.NO,
)


class InsuranceLookupItem(BaseModel):
    """Minimal {id, name} row for the "Add Insurance Lead" Category / Product pickers —
    a staff-facing read gated by `insurance_management:applications:view`, so an Employee
    with only that grant can populate the form (the Customer Portal's own
    `/customer/portal-*` endpoints are Customer-only and 403 for staff)."""

    id: str
    name: str


class InsuranceStatusUpdateRequest(BaseModel):
    """Generic Case Status control. Validated against `InsuranceStatus.ALL` first (a
    Loan status is rejected here at the schema layer); the service then only actually
    performs `fresh_lead → policy_document` — every other move has a dedicated action."""

    status: str

    @field_validator("status")
    @classmethod
    def _status_must_be_valid_insurance_status(cls, value: str) -> str:
        if value not in InsuranceStatus.ALL:
            raise ValueError(f"'{value}' is not a valid Insurance Case status.")
        return value


class MoveBackRequest(BaseModel):
    target: str = Field(pattern=f"^({InsuranceStatus.FRESH_LEAD}|{InsuranceStatus.POLICY_DOCUMENT})$")


class RestartFromReEligibleRequest(BaseModel):
    target: str = Field(pattern=f"^({InsuranceStatus.FRESH_LEAD}|{InsuranceStatus.POLICY_DOCUMENT})$")


class RejectInsuranceCaseRequest(BaseModel):
    reason: str = Field(min_length=1)
    # Insurance reject popup shows 3 / 6 / 12 / Custom / No (spec §14); the underlying
    # `ReEligibilityPeriod` enum also has 9 months (Loan) which insurance doesn't offer.
    re_eligibility: str = Field(default=ReEligibilityPeriod.NO)
    re_eligible_date: date | None = None

    @field_validator("re_eligibility")
    @classmethod
    def _valid_option(cls, value: str) -> str:
        if value not in _INSURANCE_RE_ELIGIBILITY_OPTIONS:
            raise ValueError(f"'{value}' is not a valid Re-Eligibility option.")
        return value


class PolicyLoginUpdateRequest(BaseModel):
    product_id: str | None = None
    premium_amount: float | None = Field(default=None, ge=0)
    ppt: int | None = Field(default=None, ge=1)
    pt: int | None = Field(default=None, ge=1)
    remarks: str | None = None
    policy_number: str | None = None


class ChangeProductRequest(BaseModel):
    product_id: str


class AssignInsuranceCaseRequest(BaseModel):
    """Policy Leads are assigned to Advisors (the `advisors` master), not staff users."""

    advisor_id: str = Field(min_length=1)


class HoldInsuranceCaseRequest(BaseModel):
    """Policy Lead "Place On Hold" — `reason` is one of the closed
    `InsuranceHoldReason` set. When it is `other`, `other_reason` (the free-text "Other
    Hold Reason") is mandatory and is persisted with the case's hold information."""

    reason: str
    other_reason: str | None = None
    remarks: str | None = None

    @field_validator("reason")
    @classmethod
    def _valid_reason(cls, value: str) -> str:
        if value not in InsuranceHoldReason.ALL:
            raise ValueError(f"'{value}' is not a valid Hold Reason.")
        return value

    @model_validator(mode="after")
    def _other_reason_required(self) -> "HoldInsuranceCaseRequest":
        if self.reason == InsuranceHoldReason.OTHER and not (self.other_reason or "").strip():
            raise ValueError("Other Hold Reason is required when the Hold Reason is 'Other'.")
        if self.reason != InsuranceHoldReason.OTHER:
            self.other_reason = None
        return self


class InsuranceCaseDetailsResponse(BaseModel):
    sum_insured: float | None = None
    premium_amount: float | None = None
    ppt: int | None = None
    pt: int | None = None
    policy_login_remarks: str | None = None
    policy_number: str | None = None
    policy_issued_at: datetime | None = None
    re_eligibility_choice: str | None = None
    re_eligible_date: datetime | None = None
    re_eligibility_auto_transitioned: bool = False


class RequiredDocumentsSummaryResponse(BaseModel):
    required_total: int
    verified_total: int
    all_required_verified: bool


class InsuranceCaseCountsResponse(BaseModel):
    """Server-computed Policy Leads tab badge counts — one per `InsuranceStatus.ALL`
    value, scoped identically to `list_cases` so a badge can never disagree with what its
    tab's list call returns (same principle as Loan's `GET /loan-cases/counts`)."""

    fresh_lead: int
    policy_document: int
    policy_login: int
    policy_issued: int
    re_eligible: int
    on_hold: int
    rejected: int


class InsuranceCaseListItem(BaseModel):
    id: str
    case_code: str
    application_id: str
    customer_id: str
    customer_name: str | None
    product_id: str
    product_name: str
    assigned_to: str | None
    assigned_to_name: str | None
    current_status: str
    rejection_reason: str | None
    next_follow_up_date: datetime | None = None
    created_at: datetime


class InsuranceApplicantDetailsResponse(BaseModel):
    """Extended applicant profile captured on "+ Add Insurance Lead" — all optional,
    stored in `Application.form_data`. Absent on cases created before these fields
    existed; the UI shows "—" for each missing value (never fabricated)."""

    age: int | None = None
    profession: str | None = None
    annual_income: float | None = None
    alternate_mobile: str | None = None
    height: float | None = None
    weight: float | None = None
    mother_name: str | None = None
    father_name: str | None = None
    education: str | None = None
    company_name: str | None = None
    designation: str | None = None
    nominee_name: str | None = None
    nominee_dob: date | None = None
    nominee_relationship: str | None = None
    remarks: str | None = None


class InsuranceCaseDetailResponse(InsuranceCaseListItem):
    insurance_details: InsuranceCaseDetailsResponse
    required_documents: RequiredDocumentsSummaryResponse
    updated_at: datetime
    # Populated only while `current_status == "on_hold"` (cleared on resume).
    on_hold_reason: str | None = None
    on_hold_other_reason: str | None = None
    applicant: InsuranceApplicantDetailsResponse = Field(default_factory=InsuranceApplicantDetailsResponse)


# ---------------------------------------------------------------------- manual lead creation + stage movement

class _ReEligibilityFields(BaseModel):
    reason: str | None = None
    re_eligibility: str = Field(default=ReEligibilityPeriod.NO)
    re_eligible_date: date | None = None

    @field_validator("re_eligibility")
    @classmethod
    def _valid_option(cls, value: str) -> str:
        if value not in _INSURANCE_RE_ELIGIBILITY_OPTIONS:
            raise ValueError(f"'{value}' is not a valid Re-Eligibility option.")
        return value


class CreateManualInsuranceCaseRequest(_ReEligibilityFields):
    full_name: str = Field(min_length=1, max_length=200)
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    gender: str | None = None
    age: int | None = Field(default=None, ge=18, le=120)
    profession: str | None = None
    annual_income: float | None = Field(default=None, ge=0)
    remarks: str | None = None
    insurance_category_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    stage: str = Field(default=InsuranceStatus.FRESH_LEAD)

    # Extended applicant profile — all optional; persisted into `Application.form_data`.
    alternate_mobile: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")
    height: float | None = Field(default=None, ge=0, le=300)
    weight: float | None = Field(default=None, ge=0, le=500)
    mother_name: str | None = Field(default=None, max_length=200)
    father_name: str | None = Field(default=None, max_length=200)
    education: str | None = Field(default=None, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    designation: str | None = Field(default=None, max_length=200)
    nominee_name: str | None = Field(default=None, max_length=200)
    nominee_dob: date | None = None
    nominee_relationship: str | None = Field(default=None, max_length=100)

    _APPLICANT_KEYS: ClassVar[tuple[str, ...]] = (
        "alternate_mobile", "height", "weight", "mother_name", "father_name", "education",
        "company_name", "designation", "nominee_name", "nominee_relationship",
    )

    def applicant_form_data(self) -> dict[str, Any]:
        """The extended fields to merge into `Application.form_data` — only the ones the
        staff member actually filled in (a blank field is never written)."""
        data: dict[str, Any] = {}
        for key in self._APPLICANT_KEYS:
            value = getattr(self, key)
            if isinstance(value, str):
                value = value.strip() or None
            if value is not None:
                data[key] = value
        for key in ("height", "weight"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        if self.nominee_dob is not None:
            data["nominee_dob"] = self.nominee_dob.isoformat()
        return data

    @field_validator("stage")
    @classmethod
    def _valid_stage(cls, value: str) -> str:
        if value not in _MANUAL_CREATE_STAGES:
            raise ValueError(
                "stage must be one of: "
                + ", ".join(_MANUAL_CREATE_STAGES)
                + " (Policy Login / Policy Issued are reachable only via 'Move To')."
            )
        return value

    @model_validator(mode="after")
    def _reason_required_for_rejection(self) -> "CreateManualInsuranceCaseRequest":
        if self.stage in (InsuranceStatus.REJECTED, InsuranceStatus.RE_ELIGIBLE) and not (self.reason or "").strip():
            raise ValueError("A rejection reason is required when the initial stage is Rejected or Re-Eligible.")
        return self


class MoveToStageRequest(_ReEligibilityFields):
    target: str

    @field_validator("target")
    @classmethod
    def _valid_target(cls, value: str) -> str:
        if value not in _MOVE_TO_STAGES:
            raise ValueError(f"'{value}' is not a stage a case can be moved to.")
        return value

    @model_validator(mode="after")
    def _reason_required_for_rejection(self) -> "MoveToStageRequest":
        if self.target == InsuranceStatus.REJECTED and not (self.reason or "").strip():
            raise ValueError("A rejection reason is required when moving a case to Rejected.")
        return self


# ---------------------------------------------------------------------- per-document actions

class InsuranceCaseDocumentResponse(ApplicationDocumentResponse):
    # `False` for a document whose `document_type_id` is no longer in the case's pinned
    # Product Schema — left in place after a `change_product`, shown as "Previously
    # uploaded" rather than deleted.
    is_in_schema: bool = True


class RejectCaseDocumentRequest(BaseModel):
    reason: str = Field(min_length=1)


# ---------------------------------------------------------------------- "Add Other Document" (ad-hoc, per-case)

class AddOtherDocumentRequest(BaseModel):
    name: str = Field(min_length=1)


class RejectOtherDocumentRequest(BaseModel):
    reason: str = Field(min_length=1)


class OtherDocumentUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str | None = None


class OtherDocumentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmOtherDocumentRequest(BaseModel):
    file_name: str
    content_type: str | None = None


class OtherDocumentResponse(BaseModel):
    id: str
    insurance_case_id: str
    name: str
    document_status: str
    verification_status: str
    rejection_reason: str | None
    file_name: str | None
    download_url: str | None = None
    attachment_url: str | None = None
    uploaded_at: datetime | None
    verified_at: datetime | None
    created_at: datetime
    is_current: bool = True
    doc_version: int = 1
