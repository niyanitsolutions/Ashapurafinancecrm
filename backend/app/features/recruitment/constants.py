"""Insurance Advisor Recruitment — constants.

This is a standalone domain living *inside* the Insurance Management module (it reuses
the `insurance_management` permission module, new resource `recruitment`). It is NOT a
`Lead` (no product/customer), NOT an `Application`/`ApplicationWorkflow` (no customer
portal, no `CaseType`), and NOT customer document collection. A recruitment lead is a
person applying to *become* an insurance advisor.

`RecruitmentStage` is an explicit, service-enforced state machine (same posture as
`LeadService.set_stage` — no `workflow_engine` involvement):

    FRESH ─┬─ save ──────────────► FRESH
           ├─ move_to_bop ───────► BOP
           └─ reject ────────────► REJECTED

    BOP ───┬─ back_to_fresh ─────► FRESH
           ├─ reject ────────────► REJECTED
           └─ move_to_doc_collection ► DOC_COLLECTION_EXAMINATION

    DOC_COLLECTION_EXAMINATION ─┬─ examination PASS ────► ADVISOR (+ Advisor record)
                                └─ examination FAIL/ABSENT ► DOC_COLLECTION_RE_EXAMINATION

    DOC_COLLECTION_RE_EXAMINATION ─┬─ examination PASS ──► ADVISOR (+ Advisor record)
                                   └─ examination FAIL/ABSENT ► (stays, attempt++)

The "Doc Collection" tab shows both `DOC_COLLECTION_*` stages; its Examination /
Re-Examination sub-tabs filter on the exact stage. The Agency Code sub-tab is a
read-only bookkeeping view of doc-collection leads whose latest exam is PASS but who are
not yet promoted — no business rules are invented for it.
"""


class RecruitmentStage:
    FRESH = "fresh"
    BOP = "bop"
    DOC_COLLECTION_EXAMINATION = "doc_collection_examination"
    DOC_COLLECTION_RE_EXAMINATION = "doc_collection_re_examination"
    ADVISOR = "advisor"
    REJECTED = "rejected"

    ALL = (
        FRESH,
        BOP,
        DOC_COLLECTION_EXAMINATION,
        DOC_COLLECTION_RE_EXAMINATION,
        ADVISOR,
        REJECTED,
    )
    # Both stages that render under the "Doc Collection" tab.
    DOC_COLLECTION = (DOC_COLLECTION_EXAMINATION, DOC_COLLECTION_RE_EXAMINATION)
    TERMINAL = (ADVISOR, REJECTED)


class Gender:
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

    ALL = (MALE, FEMALE, OTHER)


class Profession:
    HOUSE_WIFE = "house_wife"
    RETIRED = "retired"
    SELF_EMPLOYED = "self_employed"
    SALARIED = "salaried"
    OTHER = "other"

    ALL = (HOUSE_WIFE, RETIRED, SELF_EMPLOYED, SALARIED, OTHER)


class NomineeRelationship:
    SPOUSE = "spouse"
    FATHER = "father"
    MOTHER = "mother"
    SON = "son"
    DAUGHTER = "daughter"
    BROTHER = "brother"
    SISTER = "sister"
    OTHER = "other"

    ALL = (SPOUSE, FATHER, MOTHER, SON, DAUGHTER, BROTHER, SISTER, OTHER)


class BankProofType:
    CHEQUE = "cheque"
    PASSBOOK = "passbook"

    ALL = (CHEQUE, PASSBOOK)


class SignatureMethod:
    DRAW = "draw"
    TYPE = "type"
    UPLOAD = "upload"

    ALL = (DRAW, TYPE, UPLOAD)


class ExaminationOutcome:
    PASS = "pass"
    FAIL = "fail"
    ABSENT = "absent"

    ALL = (PASS, FAIL, ABSENT)
    # Outcomes that require the examiner to record remarks.
    REQUIRES_REMARKS = (FAIL, ABSENT)


class AdvisorChannel:
    QR = "qr"
    NON_QR = "non_qr"

    ALL = (QR, NON_QR)


class AdvisorStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"

    ALL = (ACTIVE, INACTIVE)


class AdvisorProductCategory:
    SAVINGS = "savings"
    PROTECTION = "protection"
    ULIP = "ulip"
    ANNUITY = "annuity"
    BUSINESS_INSURANCE = "business_insurance"
    CUSTOM = "custom"

    ALL = (SAVINGS, PROTECTION, ULIP, ANNUITY, BUSINESS_INSURANCE, CUSTOM)


class AdvisorFilter:
    """The Advisors list filter chips. `INDIVIDUAL` / `TOTAL_EMPLOYEES` partition by
    whether the advisor's mobile matches an `employees` row; `ACTIVE` / `INACTIVE`
    filter on `Advisor.status`. Each filter also drives its own count (scoped to the
    current QR / Non-QR sub-tab)."""

    INDIVIDUAL = "individual"
    TOTAL_EMPLOYEES = "total_employees"
    ACTIVE = "active"
    INACTIVE = "inactive"

    ALL = (INDIVIDUAL, TOTAL_EMPLOYEES, ACTIVE, INACTIVE)


class DocumentSlot:
    """Upload slots on the Recruitment Document Collection form. `PHOTO`/`SIGNATURE`
    reuse the same presigned-PUT plumbing as the four required documents."""

    PAN = "pan"
    AADHAAR = "aadhaar"
    BANK_PROOF = "bank_proof"
    QUALIFICATION = "qualification"
    PHOTO = "photo"
    SIGNATURE = "signature"

    ALL = (PAN, AADHAAR, BANK_PROOF, QUALIFICATION, PHOTO, SIGNATURE)
    # The four documents that must be present before an examination PASS is allowed.
    REQUIRED_FOR_EXAM = (PAN, AADHAAR, BANK_PROOF, QUALIFICATION)


class RecruitmentActivityType:
    CREATED = "created"
    UPDATED = "updated"
    MOVED_TO_BOP = "moved_to_bop"
    BACK_TO_FRESH = "back_to_fresh"
    MOVED_TO_DOC_COLLECTION = "moved_to_doc_collection"
    DOCUMENTS_SAVED = "documents_saved"
    EXAMINATION_RECORDED = "examination_recorded"
    MOVED_TO_ADVISOR = "moved_to_advisor"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    NOTE_ADDED = "note_added"

    ALL = (
        CREATED,
        UPDATED,
        MOVED_TO_BOP,
        BACK_TO_FRESH,
        MOVED_TO_DOC_COLLECTION,
        DOCUMENTS_SAVED,
        EXAMINATION_RECORDED,
        MOVED_TO_ADVISOR,
        REJECTED,
        ASSIGNED,
        NOTE_ADDED,
    )


class RecruitmentAuditEvent:
    LEAD_CREATED = "recruitment_lead_created"
    LEAD_UPDATED = "recruitment_lead_updated"
    STAGE_CHANGED = "recruitment_stage_changed"
    DOCUMENTS_SAVED = "recruitment_documents_saved"
    EXAMINATION_RECORDED = "recruitment_examination_recorded"
    ADVISOR_CREATED = "recruitment_advisor_created"
    ADVISOR_UPDATED = "recruitment_advisor_updated"
    ADVISOR_BUSINESS_ADDED = "recruitment_advisor_business_added"
    LEAD_ASSIGNED = "recruitment_lead_assigned"
    NOTE_ADDED = "recruitment_note_added"


# Permission wiring — reuses the existing `insurance_management` module, new resource.
PERMISSION_MODULE = "insurance_management"
PERMISSION_RESOURCE = "recruitment"
PERMISSION_ACTIONS = ("view", "create", "edit", "assign", "approve")
