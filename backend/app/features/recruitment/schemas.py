from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.features.recruitment.constants import (
    AdvisorChannel,
    AdvisorProductCategory,
    AdvisorStatus,
    BankProofType,
    DocumentSlot,
    ExaminationOutcome,
    Gender,
    NomineeRelationship,
    Profession,
    RecruitmentStage,
    SignatureMethod,
)

_MOBILE = r"^[6-9]\d{9}$"


# ---------------------------------------------------------------- requests


class CreateRecruitmentLeadRequest(BaseModel):
    full_name: str = Field(min_length=1)
    mobile: str = Field(pattern=_MOBILE)
    email: EmailStr | None = None
    gender: str = Field(pattern=f"^({'|'.join(Gender.ALL)})$")
    age: int = Field(ge=18, le=75)
    source_id: str
    profession: str = Field(pattern=f"^({'|'.join(Profession.ALL)})$")
    other_profession: str | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _other_profession_required(self) -> "CreateRecruitmentLeadRequest":
        if self.profession == Profession.OTHER and not (self.other_profession or "").strip():
            raise ValueError("other_profession is required when profession is 'other'.")
        if self.profession != Profession.OTHER:
            self.other_profession = None
        return self


class UpdateRecruitmentLeadRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1)
    mobile: str | None = Field(default=None, pattern=_MOBILE)
    email: EmailStr | None = None
    gender: str | None = Field(default=None, pattern=f"^({'|'.join(Gender.ALL)})$")
    age: int | None = Field(default=None, ge=18, le=75)
    source_id: str | None = None
    profession: str | None = Field(default=None, pattern=f"^({'|'.join(Profession.ALL)})$")
    other_profession: str | None = None
    remarks: str | None = None


class RejectRecruitmentLeadRequest(BaseModel):
    reason: str = Field(min_length=1)


class AssignRecruitmentLeadRequest(BaseModel):
    employee_id: str


class RecruitmentDocumentUploadUrlRequest(BaseModel):
    slot: str = Field(pattern=f"^({'|'.join(DocumentSlot.ALL)})$")
    file_name: str = Field(min_length=1)
    content_type: str | None = None


class RecruitmentDocumentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


class ConfirmedFile(BaseModel):
    s3_key: str
    file_name: str = Field(min_length=1)


class NomineeInput(BaseModel):
    name: str = Field(min_length=1)
    dob: date
    relationship: str = Field(pattern=f"^({'|'.join(NomineeRelationship.ALL)})$")


class SignatureInput(BaseModel):
    method: str = Field(pattern=f"^({'|'.join(SignatureMethod.ALL)})$")
    # For `type`: the typed name. For `draw`/`upload`: the confirmed S3 key of the
    # uploaded image (draw is uploaded as a PNG through the same presigned-PUT flow).
    value: str = Field(min_length=1)
    file_name: str | None = None

    @model_validator(mode="after")
    def _file_name_for_image(self) -> "SignatureInput":
        if self.method in (SignatureMethod.DRAW, SignatureMethod.UPLOAD) and not (self.file_name or "").strip():
            raise ValueError("file_name is required for a drawn or uploaded signature.")
        return self


class SaveRecruitmentDocumentsRequest(BaseModel):
    """Partial upsert — every field optional; only provided fields are written. `None`
    for a file field leaves the existing stored file untouched (use the dedicated
    remove flow if that is ever needed — not in scope here)."""

    pan: ConfirmedFile | None = None
    aadhaar: ConfirmedFile | None = None
    bank_proof: ConfirmedFile | None = None
    bank_proof_type: str | None = Field(default=None, pattern=f"^({'|'.join(BankProofType.ALL)})$")
    cheque_name_confirmed: bool | None = None
    qualification: ConfirmedFile | None = None
    photo: ConfirmedFile | None = None

    email: EmailStr | None = None
    mobile: str | None = Field(default=None, pattern=_MOBILE)
    alternate_number: str | None = Field(default=None, pattern=_MOBILE)

    nominee: NomineeInput | None = None
    signature: SignatureInput | None = None


class RecordExamFeeRequest(BaseModel):
    """Exam Fee Status → Examination. `reference` is an optional payment reference/UTR."""

    reference: str | None = None


class RecordExaminationRequest(BaseModel):
    result: str = Field(pattern=f"^({'|'.join(ExaminationOutcome.ALL)})$")
    remarks: str | None = None

    @model_validator(mode="after")
    def _remarks_required(self) -> "RecordExaminationRequest":
        if self.result in ExaminationOutcome.REQUIRES_REMARKS and not (self.remarks or "").strip():
            raise ValueError(f"remarks are required for a '{self.result}' examination result.")
        return self


class AddRecruitmentNoteRequest(BaseModel):
    text: str = Field(min_length=1)


# ---------------------------------------------------------------- responses


class RecruitmentDocumentFileResponse(BaseModel):
    file_name: str
    uploaded_at: datetime
    download_url: str | None = None


class NomineeResponse(BaseModel):
    name: str
    dob: datetime
    relationship: str


class SignatureResponse(BaseModel):
    method: str
    # For `type` the typed string; for `draw`/`upload` a presigned download URL.
    value: str
    file_name: str | None = None


class RecruitmentDocumentsResponse(BaseModel):
    pan: RecruitmentDocumentFileResponse | None = None
    aadhaar: RecruitmentDocumentFileResponse | None = None
    bank_proof: RecruitmentDocumentFileResponse | None = None
    bank_proof_type: str | None = None
    cheque_name_confirmed: bool = False
    qualification: RecruitmentDocumentFileResponse | None = None
    photo: RecruitmentDocumentFileResponse | None = None
    email: str | None = None
    mobile: str | None = None
    alternate_number: str | None = None
    nominee: NomineeResponse | None = None
    signature: SignatureResponse | None = None


class ExaminationResultResponse(BaseModel):
    attempt: int
    result: str
    remarks: str | None = None
    recorded_by: str | None = None
    recorded_at: datetime


class RecruitmentLeadListItem(BaseModel):
    id: str
    recruitment_code: str
    full_name: str
    mobile: str
    email: str | None
    gender: str
    age: int
    source_id: str
    source_name: str
    profession: str
    other_profession: str | None
    remarks: str | None
    stage: str
    assigned_to: str | None
    assigned_to_name: str | None
    latest_examination_result: str | None
    documents_ready: bool
    advisor_id: str | None
    rejected_reason: str | None
    rejected_at: datetime | None
    created_at: datetime


class RecruitmentLeadDetailResponse(RecruitmentLeadListItem):
    updated_at: datetime
    assigned_by: str | None
    assigned_at: datetime | None
    exam_fee_paid: bool = False
    exam_fee_paid_at: datetime | None = None
    exam_fee_reference: str | None = None
    documents: RecruitmentDocumentsResponse | None = None
    examinations: list[ExaminationResultResponse] = Field(default_factory=list)


class RecruitmentCountsResponse(BaseModel):
    fresh: int
    bop: int
    doc_collection: int
    exam_fee_status: int
    examination: int
    re_examination: int
    agency_code: int
    rejected: int


class RecruitmentTimelineEntryResponse(BaseModel):
    type: str  # "activity" | "note"
    event_type: str | None = None
    text: str | None = None
    metadata: dict[str, object] | None = None
    created_by: str | None
    created_at: datetime


class RecruitmentNoteResponse(BaseModel):
    id: str
    recruitment_lead_id: str
    text: str
    created_by: str | None
    created_at: datetime


class AdvisorSummaryResponse(BaseModel):
    id: str
    advisor_code: str
    recruitment_lead_id: str
    full_name: str
    mobile: str
    email: str | None
    channel: str
    agency_code: str | None
    agent_code: str | None
    status: str
    created_at: datetime


class LookupItem(BaseModel):
    id: str
    name: str


class RecruitmentLookupResponse(BaseModel):
    sources: list[LookupItem]


# ---------------------------------------------------------------- Advisor Management (Phase 2)


class UpdateAdvisorRequest(BaseModel):
    # `None` for a field = "leave unchanged". Send `agency_code=""` to clear it.
    # `channel` (QR / Non-QR "Type") and `status` are explicit, independent choices.
    # `password` is write-only — the advisor-portal credential set on the Agency Code edit
    # form. It deliberately has NO minimum-length or complexity policy (staff enter short
    # codes here); the plaintext is hashed via `hash_password`, never returned or logged,
    # and a blank value leaves the stored password unchanged. bcrypt's 72-byte hard cap is
    # still enforced by `hash_password`.
    agency_code: str | None = None
    agent_code: str | None = None
    channel: str | None = Field(default=None, pattern=f"^({'|'.join(AdvisorChannel.ALL)})$")
    password: str | None = Field(default=None, max_length=72)
    status: str | None = Field(default=None, pattern=f"^({'|'.join(AdvisorStatus.ALL)})$")


class AddAdvisorBusinessRequest(BaseModel):
    customer_name: str | None = None
    customer_mobile: str | None = Field(default=None, pattern=_MOBILE)
    policy_number: str | None = None
    product_category: str = Field(pattern=f"^({'|'.join(AdvisorProductCategory.ALL)})$")
    custom_category: str | None = None
    product_name: str = Field(min_length=1)
    premium: float = Field(ge=0)
    ppt: int = Field(ge=1)
    pt: int = Field(ge=1)
    policy_issue_date: date
    comment: str | None = None

    @model_validator(mode="after")
    def _custom_category_required(self) -> "AddAdvisorBusinessRequest":
        if self.product_category == AdvisorProductCategory.CUSTOM and not (self.custom_category or "").strip():
            raise ValueError("custom_category is required when product_category is 'custom'.")
        if self.product_category != AdvisorProductCategory.CUSTOM:
            self.custom_category = None
        return self


class AdvisorBusinessResponse(BaseModel):
    id: str
    advisor_id: str
    customer_name: str | None
    customer_mobile: str | None
    policy_number: str | None
    product_category: str
    custom_category: str | None
    product_name: str
    premium: float
    ppt: int
    pt: int
    policy_issue_date: datetime
    comment: str | None
    created_at: datetime


class AdvisorListItem(BaseModel):
    id: str
    advisor_code: str
    recruitment_lead_id: str
    full_name: str
    mobile: str
    email: str | None
    channel: str
    agency_code: str | None
    agent_code: str | None
    # Profession classification (separate from `channel`/Type and `status`). `None` for
    # advisors promoted before the field existed — the UI renders "—".
    profession: str | None
    other_profession: str | None
    status: str
    is_employee: bool
    no_of_policies: int
    total_premium: float
    created_at: datetime


class AdvisorDetailResponse(AdvisorListItem):
    updated_at: datetime
    # Linked recruitment lead (recruitment / application + documents + examination info).
    recruitment: RecruitmentLeadDetailResponse | None = None
    businesses: list[AdvisorBusinessResponse] = Field(default_factory=list)


# Re-exported for router type hints / tests.
STAGE_PATTERN = f"^({'|'.join(RecruitmentStage.ALL)})$"
ADVISOR_CHANNELS = AdvisorChannel.ALL
