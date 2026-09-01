"""Insurance Advisor Recruitment — domain models.

`RecruitmentLead` is the one aggregate root. Collected documents, examination results
and the signature all live embedded on it (a recruitment lead never has enough of them
to warrant separate collections, and keeping them embedded makes every stage transition
a single atomic document write — the production-safety requirement in the brief). The
`Advisor` a passing candidate becomes is its own collection, keyed uniquely on
`recruitment_lead_id` so a PASS can never mint two advisor records.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.features.recruitment.constants import RecruitmentStage
from app.shared.base_document import BaseDocument


class RecruitmentDocumentFile(BaseModel):
    """One uploaded file. Only the S3 key/name is persisted — the bytes go straight to
    S3 via a presigned PUT, exactly like `ApplicationDocument.s3_key` (Module 6B)."""

    s3_key: str
    file_name: str
    uploaded_at: datetime
    uploaded_by: str | None = None


class RecruitmentNominee(BaseModel):
    name: str
    # UTC instant of IST midnight for the nominee's DOB calendar date — never a naive
    # date (same convention as `Lead.next_follow_up_date`, via `ist_date_to_utc_midnight`).
    dob: datetime
    relationship: str  # NomineeRelationship.ALL


class RecruitmentSignature(BaseModel):
    """Exactly one active signature representation per lead. `draw`/`upload` store an
    S3 key in `value`; `type` stores the typed string. Switching method wholesale
    replaces this object — there is never more than one active signature."""

    method: str  # SignatureMethod.ALL
    value: str
    file_name: str | None = None  # set for draw/upload only
    updated_at: datetime
    updated_by: str | None = None


class RecruitmentDocuments(BaseModel):
    """Everything captured on the Recruitment Document Collection form. All optional —
    the form is filled progressively; completeness is only enforced at the
    examination-PASS gate (see `RecruitmentService._assert_ready_for_pass`)."""

    pan: RecruitmentDocumentFile | None = None
    aadhaar: RecruitmentDocumentFile | None = None
    bank_proof: RecruitmentDocumentFile | None = None
    bank_proof_type: str | None = None  # BankProofType.ALL
    # A cheque is only a valid bank proof if it carries the printed account-holder name;
    # the collecting staff member attests to that here. `verify`/PASS reject an
    # unconfirmed cheque.
    cheque_name_confirmed: bool = False
    qualification: RecruitmentDocumentFile | None = None
    photo: RecruitmentDocumentFile | None = None

    email: str | None = None
    mobile: str | None = None
    alternate_number: str | None = None

    nominee: RecruitmentNominee | None = None
    signature: RecruitmentSignature | None = None


class ExaminationResult(BaseModel):
    """Append-only history entry — one per examination attempt."""

    attempt: int
    result: str  # ExaminationOutcome.ALL
    remarks: str | None = None  # required for FAIL/ABSENT (enforced in service + schema)
    recorded_by: str | None = None
    recorded_at: datetime


class RecruitmentLead(BaseDocument):
    recruitment_code: str  # AFS-RCT-000001, auto-generated

    full_name: str
    mobile: str
    email: str | None = None
    gender: str  # Gender.ALL
    age: int

    source_id: str  # ref: system_settings.lead_sources (reused, read-only)

    profession: str  # Profession.ALL
    other_profession: str | None = None  # required iff profession == Profession.OTHER

    remarks: str | None = None

    stage: str = Field(default=RecruitmentStage.FRESH, pattern=f"^({'|'.join(RecruitmentStage.ALL)})$")

    assigned_to: str | None = None  # ref: employees, nullable
    assigned_by: str | None = None  # actor User id
    assigned_at: datetime | None = None

    rejected_reason: str | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None

    # Set once the lead is promoted to an Advisor — the idempotency guard that makes
    # "examination PASS" and "manual Move to Advisor" safe to trigger repeatedly.
    advisor_id: str | None = None

    documents: RecruitmentDocuments | None = None
    examinations: list[ExaminationResult] = Field(default_factory=list)


class RecruitmentActivity(BaseDocument):
    recruitment_lead_id: str
    event_type: str = Field(pattern=r"^[a-z_]+$")
    metadata: dict[str, object] | None = None


class RecruitmentNote(BaseDocument):
    recruitment_lead_id: str
    text: str


class Advisor(BaseDocument):
    advisor_code: str  # AFS-ADV-000001, auto-generated
    recruitment_lead_id: str  # unique — one advisor per recruitment lead

    full_name: str
    mobile: str
    email: str | None = None

    # `channel` is DERIVED from `agency_code` (Phase 2 decision): an advisor is "qr" once
    # an agency code is assigned, "non_qr" until then. Kept as a stored field, always
    # written in lockstep with `agency_code` (see AdvisorService.update_advisor), so the
    # QR / Non-QR tabs stay a plain indexed query.
    channel: str = "non_qr"  # AdvisorChannel.ALL
    agency_code: str | None = None
    # `status` ("active" default) comes from BaseDocument; "inactive" is also supported.
    # No stored policy count / premium total — aggregated from `advisor_business` records
    # (brief §37: prefer reliable aggregation over denormalized totals).


class AdvisorBusiness(BaseDocument):
    """One policy / business record produced by an advisor. The advisor's policy count
    and total premium are always aggregated from these — never stored on `Advisor`."""

    advisor_id: str

    product_category: str  # AdvisorProductCategory.ALL
    # Free-text category name, required iff product_category == "custom".
    custom_category: str | None = None
    product_name: str

    premium: float  # >= 0 — matches every existing money field (no Decimal in this codebase)
    ppt: int  # premium paying term, whole years, >= 1
    pt: int  # policy term, whole years, >= 1
    # IST-midnight UTC (via app.utils.datetime.ist_date_to_utc_midnight), same convention
    # as RecruitmentNominee.dob / Lead.next_follow_up_date.
    policy_issue_date: datetime

    comment: str | None = None
