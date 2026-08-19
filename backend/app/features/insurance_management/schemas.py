from datetime import datetime

from pydantic import BaseModel, field_validator

from app.features.workflow_engine.constants import InsuranceStatus


class InsuranceStatusUpdateRequest(BaseModel):
    """Backs the generic Case Status control on the Insurance Case detail page —
    validated against `InsuranceStatus.ALL` only, so a Loan status value (or any other
    string) is rejected here at the schema layer, before the service layer even runs the
    existing `WorkflowEngine` transition-graph check. See
    `InsuranceCaseService.update_status`'s own docstring for why only some transitions
    actually succeed through this endpoint."""

    status: str

    @field_validator("status")
    @classmethod
    def _status_must_be_valid_insurance_status(cls, value: str) -> str:
        if value not in InsuranceStatus.ALL:
            raise ValueError(f"'{value}' is not a valid Insurance Case status.")
        return value


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
