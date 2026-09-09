from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.workflow_engine.constants import (
    BankOfferDecision,
    LoanStatus,
    ReEligibilityPeriod,
    TopUpPeriod,
)


class _ReEligibilitySchedulingFields(BaseModel):
    """Reject → Re-Eligibility scheduling, shared by the generic status control and Final
    Evaluation's reject decision. Both fields are optional at the schema layer (the same
    request shapes carry non-reject transitions); `LoanCaseService` enforces that a
    Re-Eligibility choice is mandatory *when the target is `rejected`*, exactly like the
    existing "rejection reason is mandatory" rule. `re_eligible_date` is only meaningful
    with `re_eligibility="custom"`."""

    re_eligibility: str | None = None
    re_eligible_date: date | None = None

    @field_validator("re_eligibility")
    @classmethod
    def _choice_must_be_valid(cls, value: str | None) -> str | None:
        if value is not None and value not in ReEligibilityPeriod.ALL:
            raise ValueError(f"'{value}' is not a valid Re-Eligibility option.")
        return value

    @model_validator(mode="after")
    def _custom_date_required_iff_custom(self) -> "_ReEligibilitySchedulingFields":
        if self.re_eligibility == ReEligibilityPeriod.CUSTOM and self.re_eligible_date is None:
            raise ValueError("re_eligible_date is required when re_eligibility is 'custom'.")
        if self.re_eligibility != ReEligibilityPeriod.CUSTOM:
            self.re_eligible_date = None
        return self


class LoanStatusUpdateRequest(_ReEligibilitySchedulingFields):
    """Backs the generic Case Status control on the Loan Case detail page — validated
    against `LoanStatus.ALL` only, so an Insurance status value (or any other string) is
    rejected here at the schema layer, before the service layer even runs the existing
    `WorkflowEngine` transition-graph check. See `LoanCaseService.update_status`'s own
    docstring for why only some transitions actually succeed through this endpoint."""

    status: str
    remarks: str | None = None

    @field_validator("status")
    @classmethod
    def _status_must_be_valid_loan_status(cls, value: str) -> str:
        if value not in LoanStatus.ALL:
            raise ValueError(f"'{value}' is not a valid Loan Case status.")
        return value


class OverrideStageRequest(BaseModel):
    """"Staff Override — Skip Stage Validations": a deliberate administrative move to any
    Loan stage (except `on_hold`, which has its own Hold/Resume actions). `reason` is
    optional — the audit trail records the override either way."""

    status: str
    reason: str | None = None

    @field_validator("status")
    @classmethod
    def _valid_override_target(cls, value: str) -> str:
        if value not in LoanStatus.ALL or value == LoanStatus.ON_HOLD:
            raise ValueError(f"'{value}' is not a Loan stage a Staff Override can move a case to.")
        return value


class NewCustomerDetailsRequest(BaseModel):
    """New Customer's bank/branch/loan-type/amount preferences — captured only while the
    case is at `new_customer`; recording it always advances the case to
    `credit_evaluation` (decision #132, superseding the old bodiless
    `_PLAIN_TRANSITIONS` move for this pair). All fields optional — this is an initial
    intake preference, not a hard gate."""

    preferred_bank_name: str | None = None
    preferred_branch: str | None = None
    loan_type: str | None = None
    requested_amount: float | None = None
    preferred_remarks: str | None = None


class CreditEvaluationRequest(BaseModel):
    """Case-level credit score/remarks only (decision #129) — data capture, independent
    of any individual bank/NBFC's own decision (`BankOfferRequest.decision`, below) and
    never itself moves the case out of Credit Evaluation. The case advances only via a
    bank-offer selection (`POST .../bank-offers/{offer_id}/select`) or the generic plain
    status update (Rejected/Re-Eligible)."""

    credit_score: int | None = None
    credit_remarks: str | None = None


class BankOfferRequest(BaseModel):
    """Add or edit one bank/NBFC's offer on a Loan Case — a case can carry any number of
    these; adding one never overwrites another (decision #129, superseding the old
    single-slot `BankDetailsRequest`/`OfferRequest` flow for Credit Evaluation/Offer
    Acceptance). Now also the New Customer stage's own bank/NBFC capture (this round):
    `branch`/`loan_type`/`requested_amount` are populated there; `decision` is left
    `None` (persisted as `pending`) until a real Credit Evaluation decision is made."""

    bank_name: str
    branch: str | None = None
    loan_type: str | None = None
    requested_amount: float | None = None
    bank_application_id: str | None = None
    reference_number: str | None = None
    assigned_officer: str | None = None
    decision: str | None = None
    approved_amount: float | None = None
    interest_rate: float | None = None
    tenure_months: int | None = None
    processing_fee: float | None = None
    emi_per_month: float | None = None
    remarks: str | None = None

    @field_validator("decision")
    @classmethod
    def _decision_must_be_valid(cls, value: str | None) -> str:
        value = value or BankOfferDecision.PENDING
        if value not in BankOfferDecision.ALL:
            raise ValueError(f"'{value}' is not a valid bank offer decision.")
        return value

    @model_validator(mode="after")
    def _approved_amount_and_emi_required_iff_approved(self) -> "BankOfferRequest":
        if self.decision == BankOfferDecision.APPROVED:
            if self.approved_amount is None:
                raise ValueError("approved_amount is required when decision is 'approved'.")
            if self.emi_per_month is None:
                raise ValueError("emi_per_month is required when decision is 'approved'.")
        else:
            self.approved_amount = None
            self.emi_per_month = None
        return self


class RvOvRefRequest(BaseModel):
    """Residence/Office Verification and Reference-check stage data — captured only while
    the case is at `rv_ov_ref`; recording it advances the case to `esign_nach_kyc`."""

    rv_ov_ref_type: str
    rv_ov_ref_status: str
    rv_ov_ref_date: datetime
    rv_ov_ref_verified_by: str
    rv_ov_ref_result: str
    rv_ov_ref_remarks: str | None = None


class EsignNachKycRequest(BaseModel):
    esign_completed: bool = False
    nach_completed: bool = False
    kyc_completed: bool = False


class FinalEvaluationRequest(_ReEligibilitySchedulingFields):
    remarks: str | None = None
    decision: str  # "approved" | "rejected"
    rejection_reason: str | None = None


class DisburseRequest(BaseModel):
    disbursed_amount: float
    disbursed_reference: str


class LoanCaseDetailsResponse(BaseModel):
    preferred_bank_name: str | None
    preferred_branch: str | None
    loan_type: str | None
    requested_amount: float | None
    preferred_remarks: str | None
    credit_score: int | None
    credit_remarks: str | None
    bank_nbfc_name: str | None
    bank_application_id: str | None
    bank_reference_number: str | None
    assigned_officer: str | None
    bank_decision: str | None
    bank_remarks: str | None
    offered_amount: float | None
    offered_tenure_months: int | None
    offered_interest_rate: float | None
    offer_decision: str
    rv_ov_ref_type: str | None
    rv_ov_ref_status: str | None
    rv_ov_ref_date: datetime | None
    rv_ov_ref_verified_by: str | None
    rv_ov_ref_result: str | None
    rv_ov_ref_remarks: str | None
    esign_completed: bool
    nach_completed: bool
    kyc_completed: bool
    final_evaluation_remarks: str | None
    re_eligibility_choice: str | None = None
    re_eligible_date: datetime | None = None
    re_eligibility_scheduled_at: datetime | None = None
    re_eligibility_scheduled_by: str | None = None
    re_eligibility_auto_transitioned: bool = False
    disbursed_amount: float | None
    disbursed_at: datetime | None
    disbursed_reference: str | None
    top_up_period: str | None = None
    top_up_eligibility_date: datetime | None = None
    top_up_remarks: str | None = None
    top_up_scheduled_at: datetime | None = None
    top_up_scheduled_by: str | None = None


class LoanCaseListItem(BaseModel):
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
    allowed_next_statuses: list[str] = Field(default_factory=list)
    selected_bank_name: str | None = None
    approved_amount: float | None = None
    disbursed_amount: float | None = None
    disbursed_at: datetime | None = None
    next_follow_up_date: datetime | None = None
    created_at: datetime


class LoanCaseCustomerSummary(BaseModel):
    """Requirement 21.B — the customer profile already collected before Loan Management,
    surfaced read-only here (never edited through this module)."""

    full_name: str
    mobile: str
    email: str | None
    date_of_birth: datetime | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    pincode: str | None


class LoanCaseApplicationSummary(BaseModel):
    """Requirement 21.C — the underlying Application's own fields, read-only."""

    application_code: str
    product_category: str
    status: str
    submitted_at: datetime | None


class BankOfferResponse(BaseModel):
    """Full, staff-only view of one bank offer."""

    id: str
    loan_case_id: str
    bank_name: str
    branch: str | None
    loan_type: str | None
    requested_amount: float | None
    bank_application_id: str | None
    reference_number: str | None
    assigned_officer: str | None
    decision: str
    approved_amount: float | None
    interest_rate: float | None
    tenure_months: int | None
    processing_fee: float | None
    emi_per_month: float | None
    remarks: str | None
    is_selected: bool
    selected_at: datetime | None
    selected_by: str | None
    created_at: datetime
    updated_at: datetime


class LoanCaseDetailResponse(LoanCaseListItem):
    pending_document_type_ids: list[str]
    loan_details: LoanCaseDetailsResponse
    updated_at: datetime
    allowed_previous_statuses: list[str] = Field(default_factory=list)
    customer: LoanCaseCustomerSummary | None = None
    application: LoanCaseApplicationSummary | None = None
    bank_offers: list[BankOfferResponse] = Field(default_factory=list)


class AdditionalDocumentRequest(BaseModel):
    name: str = Field(min_length=1)


class RejectAdditionalDocumentRequest(BaseModel):
    reason: str = Field(min_length=1)


class AdditionalDocumentUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str | None = None


class AdditionalDocumentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmAdditionalDocumentRequest(BaseModel):
    file_name: str
    # Accepted for symmetry with Module 6B's `ConfirmDocumentRequest` but never trusted —
    # the real S3 key is re-derived server-side, same reasoning as that schema.
    s3_key: str
    content_type: str | None = None


class AdditionalDocumentResponse(BaseModel):
    id: str
    loan_case_id: str
    name: str
    document_status: str
    verification_status: str
    rejection_reason: str | None
    file_name: str | None
    download_url: str | None = None
    attachment_url: str | None = None
    uploaded_at: datetime | None
    verified_by_name: str | None = None
    verified_at: datetime | None
    created_at: datetime


class CaseRemarksRequest(BaseModel):
    """Generic optional-remarks body — used by both `move_to_credit_evaluation` (a
    forward move) and `move_back` (this round's new backward move); neither carries any
    other data."""

    remarks: str | None = None


class LoanFollowUpRequest(BaseModel):
    """Re-Eligible Case Management enhancement — a follow-up comment + optional follow-up
    date. Never overwrites a prior comment (each is a new `ApplicationNote`). `follow_up_date`
    is a plain calendar date and may be in the past (staff log past outcomes too)."""

    comment: str = Field(min_length=1)
    follow_up_date: date | None = None


class ScheduleTopUpRequest(BaseModel):
    """Backs both entry points into the Top Up scheduling popup: the "Top Up" action on
    a Disbursed row (initial scheduling) and "Rejected" on a Top Up Loan row (reject +
    reschedule) — same popup, same request shape, same endpoint (`LoanCaseService.
    schedule_top_up`), per spec. `custom_date` is required only when `period="custom"`;
    the service validates it isn't before the case's own `disbursed_at`."""

    period: str
    custom_date: date | None = None
    remarks: str | None = None

    @field_validator("period")
    @classmethod
    def _period_must_be_valid(cls, value: str) -> str:
        if value not in TopUpPeriod.ALL:
            raise ValueError(f"'{value}' is not a valid Top Up period.")
        return value

    @model_validator(mode="after")
    def _custom_date_required_iff_custom(self) -> "ScheduleTopUpRequest":
        if self.period == TopUpPeriod.CUSTOM and self.custom_date is None:
            raise ValueError("custom_date is required when period is 'custom'.")
        if self.period != TopUpPeriod.CUSTOM:
            self.custom_date = None
        return self


class DisbursementItem(BaseModel):
    id: str
    case_code: str
    customer_name: str | None
    product_name: str
    approved_amount: float | None
    disbursed_amount: float | None
    disbursed_reference: str | None
    disbursed_at: datetime | None


class DisbursementListResponse(BaseModel):
    """List + aggregate from the SAME filtered query (requirement 29) — the card and the
    table can never disagree because they're read off this one response."""

    items: list[DisbursementItem]
    total_count: int
    total_amount: float


class CustomerBankOfferResponse(BaseModel):
    """Customer-facing view — approved offers only, trimmed to exactly the fields the
    spec allows a customer to see (bank + full offer economics). No
    bank_application_id/reference_number/assigned_officer/remarks/decision — those stay
    staff-only (decision #129)."""

    id: str
    bank_name: str
    approved_amount: float
    interest_rate: float | None
    tenure_months: int | None
    processing_fee: float | None
    emi_per_month: float | None


class LoanCaseCountsResponse(BaseModel):
    """Server-computed tab badge counts — one per `LoanStatus.ALL` value, same
    "never trust the currently-loaded page" principle Leads' `GET /leads/counts`
    established (decision #125)."""

    new_customer: int
    credit_evaluation: int
    offer_acceptance: int
    additional_documents: int
    rv_ov_ref: int
    esign_nach_kyc: int
    final_evaluation: int
    send_for_disbursement: int
    disbursed: int
    on_hold: int
    re_eligible: int
    rejected: int
    # Not a `LoanStatus.ALL` member — a derived count over currently-`disbursed` cases
    # whose `top_up_eligibility_date` has been reached (see
    # LoanCaseService.count_top_up_eligible_cases). Kept alongside the status counts on
    # this one response so the Top Up Loan tab badge is fetched from the exact same call
    # as every other tab's.
    top_up_eligible: int = 0
