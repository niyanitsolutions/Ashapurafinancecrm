from datetime import datetime

from pydantic import BaseModel


class BankDetailsRequest(BaseModel):
    bank_nbfc_name: str | None = None
    bank_application_id: str | None = None
    bank_reference_number: str | None = None
    assigned_officer: str | None = None
    bank_decision: str | None = None
    bank_remarks: str | None = None


class CreditEvaluationRequest(BaseModel):
    credit_score: int | None = None
    credit_remarks: str | None = None
    decision: str  # "approved" | "rejected"
    rejection_reason: str | None = None


class OfferRequest(BaseModel):
    offered_amount: float
    offered_tenure_months: int
    offered_interest_rate: float


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
    created_at: datetime


class LoanCaseDetailResponse(LoanCaseListItem):
    pending_document_type_ids: list[str]
    loan_details: LoanCaseDetailsResponse
    updated_at: datetime
