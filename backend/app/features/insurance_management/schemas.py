from datetime import datetime

from pydantic import BaseModel


class UnderwritingRequest(BaseModel):
    sum_insured: float | None = None
    underwriting_remarks: str | None = None
    requires_medical: bool = False
    requires_additional_documents: bool = False
    decision: str  # "approved" | "rejected"
    rejection_reason: str | None = None


class MedicalVerificationRequest(BaseModel):
    outcome: str  # "cleared" | "failed"
    medical_remarks: str | None = None
    rejection_reason: str | None = None


class PremiumRequest(BaseModel):
    premium_amount: float


class GeneratePolicyRequest(BaseModel):
    policy_number: str


class InsuranceCaseDetailsResponse(BaseModel):
    sum_insured: float | None
    underwriting_remarks: str | None
    requires_medical: bool
    requires_additional_documents: bool
    medical_verification_outcome: str | None
    medical_verification_remarks: str | None
    premium_amount: float | None
    premium_decision: str
    policy_number: str | None
    policy_generated_at: datetime | None
    policy_issued_at: datetime | None


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
    created_at: datetime


class InsuranceCaseDetailResponse(InsuranceCaseListItem):
    pending_document_type_ids: list[str]
    insurance_details: InsuranceCaseDetailsResponse
    updated_at: datetime
