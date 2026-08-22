from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.features.workflow_engine.constants import BankOfferDecision, LoanStatus


class LoanStatusUpdateRequest(BaseModel):
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


class BankDetailsRequest(BaseModel):
    bank_nbfc_name: str | None = None
    bank_application_id: str | None = None
    bank_reference_number: str | None = None
    assigned_officer: str | None = None
    bank_decision: str | None = None
    bank_remarks: str | None = None


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
    Acceptance)."""

    bank_name: str
    bank_application_id: str | None = None
    reference_number: str | None = None
    assigned_officer: str | None = None
    decision: str
    approved_amount: float | None = None
    remarks: str | None = None

    @field_validator("decision")
    @classmethod
    def _decision_must_be_valid(cls, value: str) -> str:
        if value not in BankOfferDecision.ALL:
            raise ValueError(f"'{value}' is not a valid bank offer decision.")
        return value

    @model_validator(mode="after")
    def _approved_amount_required_iff_approved(self) -> "BankOfferRequest":
        if self.decision == BankOfferDecision.APPROVED and self.approved_amount is None:
            raise ValueError("approved_amount is required when decision is 'approved'.")
        if self.decision != BankOfferDecision.APPROVED:
            self.approved_amount = None
        return self


class EsignNachKycRequest(BaseModel):
    esign_completed: bool = False
    nach_completed: bool = False
    kyc_completed: bool = False


class FinalEvaluationRequest(BaseModel):
    remarks: str | None = None
    decision: str  # "approved" | "rejected"
    rejection_reason: str | None = None


class DisburseRequest(BaseModel):
    disbursed_amount: float
    disbursed_reference: str


class LoanCaseDetailsResponse(BaseModel):
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
    esign_completed: bool
    nach_completed: bool
    kyc_completed: bool
    final_evaluation_remarks: str | None
    disbursed_amount: float | None
    disbursed_at: datetime | None
    disbursed_reference: str | None


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
    selected_bank_name: str | None = None
    approved_amount: float | None = None
    created_at: datetime


class LoanCaseDetailResponse(LoanCaseListItem):
    pending_document_type_ids: list[str]
    loan_details: LoanCaseDetailsResponse
    updated_at: datetime


class BankOfferResponse(BaseModel):
    """Full, staff-only view of one bank offer."""

    id: str
    loan_case_id: str
    bank_name: str
    bank_application_id: str | None
    reference_number: str | None
    assigned_officer: str | None
    decision: str
    approved_amount: float | None
    remarks: str | None
    is_selected: bool
    selected_at: datetime | None
    selected_by: str | None
    created_at: datetime
    updated_at: datetime


class CustomerBankOfferResponse(BaseModel):
    """Customer-facing view — approved offers only, trimmed to exactly the fields the
    spec allows a customer to see. No bank_application_id/reference_number/
    assigned_officer/remarks/decision — those are staff-only (decision #129)."""

    id: str
    bank_name: str
    approved_amount: float


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
