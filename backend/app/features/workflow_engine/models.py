"""Module 6C domain models. One unified `ApplicationWorkflow` collection covers both
Loan and Insurance cases (a case-type discriminator, `case_type`), rather than two
separate collections — the "engine is code, catalog is data" split used since Access
Control's `PermissionEngine`/`Permission` and 6B's Dynamic Form Engine, extended here:
`WorkflowDefinition` rows (one per case_type+status) ARE the workflow, and this module's
`WorkflowEngine` (engine.py) is the generic code that walks them for any case type,
current and future.

Reverse-pointer at Module 6B's frozen `Application` (`application_id`) — 6B is not
modified, the same pattern 6B itself used against 6A's frozen `Lead`.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.features.workflow_engine.constants import CaseType, OfferDecision
from app.shared.base_document import BaseDocument


class WorkflowDefinition(BaseDocument):
    """One row per (case_type, status): the *data* half of the workflow engine. Adding a
    new case type or amending Insurance's proposed stages is a data change here, not new
    branching code — see docs/decisions/DECISIONS.md for Module 6C.
    """

    case_type: str = Field(pattern=f"^({'|'.join(CaseType.ALL)})$")
    status: str
    label: str
    sequence: int
    allowed_next_statuses: list[str] = Field(default_factory=list)
    # Always empty in v1 — no status supports rollback this round (business decision).
    # Kept on the schema so a future round can define specific rollback paths without a
    # schema change, per the brief's own "Allowed Previous Status (if rollback is
    # permitted)" requirement.
    allowed_previous_statuses: list[str] = Field(default_factory=list)
    required_permission: str | None = None  # documentation only — "module:resource:action"; actual
    # enforcement is each endpoint's own `require_permission(...)` dependency (no dynamic
    # permission lookup — "no new authorization mechanism" per the brief).
    customer_editable: bool = False
    employee_editable: bool = True
    audit_event: str
    # Both placeholders only — no Notification Management / Reminder Engine module exists
    # yet to consume them (explicitly out of scope for 6C). Stored so those future modules
    # can wire real behavior without a schema change here.
    notification_trigger_key: str | None = None
    reminder_trigger_key: str | None = None


class LoanCaseDetails(BaseModel):
    """Loan-specific fields, embedded on `ApplicationWorkflow` when `case_type="loan"`.
    Credit evaluation / eSign / NACH / KYC are staff-recorded manually — no live credit
    bureau, e-sign, or NACH provider integration exists in this project yet; see
    docs/KNOWN_LIMITATIONS.md."""

    # New Customer stage preferences (decision #132) — captured by
    # `LoanCaseService.record_new_customer_details` when transitioning out of
    # `new_customer`. Deliberately NOT reusing bank_nbfc_name/bank_application_id/etc.
    # below — those are exclusively written by `_select_bank_offer_core`'s bank-offer
    # selection at Credit Evaluation (decision #129), a different concept at a different
    # stage; writing both to the same field would create ambiguity about which stage's
    # data is currently present.
    preferred_bank_name: str | None = None
    preferred_branch: str | None = None
    loan_type: str | None = None
    requested_amount: float | None = None
    preferred_remarks: str | None = None

    credit_score: int | None = None
    credit_remarks: str | None = None

    bank_nbfc_name: str | None = None
    bank_application_id: str | None = None
    bank_reference_number: str | None = None
    assigned_officer: str | None = None
    bank_decision: str | None = None
    bank_remarks: str | None = None

    offered_amount: float | None = None
    offered_tenure_months: int | None = None
    offered_interest_rate: float | None = None
    offer_decision: str = Field(default=OfferDecision.PENDING, pattern=f"^({'|'.join(OfferDecision.ALL)})$")

    rv_ov_ref_type: str | None = None
    rv_ov_ref_status: str | None = None
    rv_ov_ref_date: datetime | None = None
    rv_ov_ref_verified_by: str | None = None
    rv_ov_ref_result: str | None = None
    rv_ov_ref_remarks: str | None = None

    esign_completed: bool = False
    nach_completed: bool = False
    kyc_completed: bool = False

    final_evaluation_remarks: str | None = None

    # Reject → Re-Eligibility scheduling (production add-on). Set whenever a case enters
    # `rejected` via the Reject popup (any stage) or Final Evaluation's reject decision —
    # see `LoanCaseService._apply_re_eligibility_schedule`. `re_eligibility_choice` is a
    # `ReEligibilityPeriod` value; `"no"` (or None) means "never automatically
    # Re-Eligible". `re_eligible_date` is UTC-midnight of the IST target date, consumed
    # by the `auto_transition_re_eligible_cases` worker job which flips the case
    # `rejected -> re_eligible` on/after that instant and then clears the date.
    # `re_eligibility_auto_transitioned` records that that automatic move happened (vs a
    # staff "Mark Re-Eligible"). All optional/default so every case rejected before this
    # existed is unaffected (never auto Re-Eligible) with no migration.
    re_eligibility_choice: str | None = None
    re_eligible_date: datetime | None = None
    re_eligibility_scheduled_at: datetime | None = None
    re_eligibility_scheduled_by: str | None = None
    re_eligibility_auto_transitioned: bool = False

    disbursed_amount: float | None = None
    disbursed_at: datetime | None = None
    disbursed_reference: str | None = None

    # Top Up Loan — a disbursed case remains `current_status=DISBURSED` forever (a Top
    # Up decision is never a WorkflowEngine status transition); eligibility is a
    # derived, read-time check (`disbursed` status + `top_up_eligibility_date` reached),
    # never a new status of its own. `top_up_period`/`top_up_eligibility_date` always
    # reflect the LAST scheduling decision (the original one made right after
    # disbursement, or any later reject/reschedule from the Top Up Loan tab — repeated
    # cycles simply overwrite these, with each decision preserved in the case's own
    # ApplicationStatusHistory/ApplicationNote timeline via LoanCaseService.
    # schedule_top_up, never a second history mechanism). `top_up_eligibility_date=None`
    # means no Top Up is currently scheduled — never scheduled yet, "No" was selected, or
    # this Top Up slot was already consumed by "Move to Document Collection". All fields
    # optional/default None so every case disbursed before this existed keeps behaving
    # exactly as before (never Top Up eligible) with no migration required.
    top_up_period: str | None = None  # TopUpPeriod: "3_months" | "6_months" | "12_months" | "no" | "custom"
    top_up_eligibility_date: datetime | None = None
    top_up_remarks: str | None = None
    top_up_scheduled_at: datetime | None = None
    top_up_scheduled_by: str | None = None  # ref: users — who made the last scheduling decision


class InsuranceCaseDetails(BaseModel):
    """Insurance-specific fields, embedded on `ApplicationWorkflow` when
    `case_type="insurance"`. `requires_medical`/`requires_additional_documents` are
    per-case judgment calls recorded by the underwriter during Underwriting (not fixed
    product attributes) — see docs/decisions/DECISIONS.md, since Module 4's
    `InsuranceProduct` (frozen) is not modified to carry either flag. `policy_number`/
    `policy_generated_at` (Policy Generation) and `policy_issued_at` (Policy Issued) are
    deliberately two distinct events, not one — decision 064."""

    sum_insured: float | None = None
    underwriting_remarks: str | None = None
    requires_medical: bool = False
    requires_additional_documents: bool = False
    medical_verification_outcome: str | None = None  # "cleared" | "failed"
    medical_verification_remarks: str | None = None

    premium_amount: float | None = None
    premium_decision: str = Field(default=OfferDecision.PENDING, pattern=f"^({'|'.join(OfferDecision.ALL)})$")

    policy_number: str | None = None
    policy_generated_at: datetime | None = None
    policy_issued_at: datetime | None = None


class ApplicationWorkflow(BaseDocument):
    case_code: str  # AFS-LOAN-000001 / AFS-INS-000001
    case_type: str = Field(pattern=f"^({'|'.join(CaseType.ALL)})$")

    application_id: str  # ref: customer.applications (Module 6B, frozen, read-only) — 1:1
    customer_id: str  # denormalized from Application, same convention Application itself uses
    product_id: str
    product_category: str

    assigned_to: str | None = None  # ref: employees — inherited from Application.assigned_to at
    # creation, independently reassignable afterward (confirmed by the user: "Owner can
    # reassign. Every reassignment must be audited.")

    # Loan-only eligibility gate (decision #130, revised by the "DC vs LM" production
    # fix): null means "not yet eligible to appear in Loan Management." Every new case
    # starts null regardless of origin. A Lead-originated application is ungated by
    # `LeadService.set_stage`'s loan_management branch; a Lead-less application is
    # ungated by `LeadService.move_lead_less_application_to_loan_management` — both
    # enforce the identical submitted+all-required-documents-verified gate, and both are
    # what makes an application visible in Document Collection until this is set (see
    # `LeadService._lead_less_document_collection_pool` for the Lead-less half).
    # Insurance cases never set or read this field.
    moved_to_loan_management_at: datetime | None = None

    current_status: str
    rejection_reason: str | None = None  # mandatory whenever current_status == "rejected"

    # Re-Eligible Case Management enhancement — denormalised "the case's current follow-up
    # plan": the `follow_up_date` of the most recently added dated follow-up note (mirrors
    # how `Lead.next_follow_up_date` is overwritten by `LeadService.set_follow_up`). Read
    # by the Re-Eligible list's "Next Follow-up" column so it needs no per-row note query.
    next_follow_up_date: datetime | None = None

    # Populated only while current_status == "on_hold" (workflow_engine/hold.py);
    # cleared on resume. `on_hold_previous_status` is what `resume` transitions back
    # into — an Optional Status on the workflow definition, not a hardcoded branch.
    on_hold_reason: str | None = None
    on_hold_previous_status: str | None = None
    on_hold_since: datetime | None = None

    # Document types an Employee has requested for the CURRENT stage but that aren't yet
    # fulfilled by a matching upload — cleared once verified. Reuses Module 6B's own,
    # unmodified `application_documents`/upload endpoints (same application_id) rather
    # than duplicating file-storage plumbing.
    pending_document_type_ids: list[str] = Field(default_factory=list)

    loan_details: LoanCaseDetails | None = None
    insurance_details: InsuranceCaseDetails | None = None

    extra: dict[str, Any] = Field(default_factory=dict)  # unused reserved slot — kept empty


class ApplicationStatusHistory(BaseDocument):
    """Append-only transition log — doubles as the Case Timeline's status half (merged
    with `ApplicationNote`, same pattern as Module 6A's Lead Timeline, decision 042)."""

    application_workflow_id: str
    case_type: str
    from_status: str | None
    to_status: str
    remarks: str | None = None
    # changed_by = created_by, changed_at = created_at (BaseDocument fields)


class ApplicationNote(BaseDocument):
    application_workflow_id: str
    text: str
    # Re-Eligible Case Management enhancement — a follow-up comment carries the date staff
    # want to next act on the case. UTC-midnight of the IST calendar date (same convention
    # as `Lead.next_follow_up_date`); None for a plain note. The Past/Today/Future colour
    # is computed at render time from this, never stored.
    follow_up_date: datetime | None = None
    # created_by = author, created_at = when (BaseDocument fields)


class ApplicationDecision(BaseDocument):
    """A structured record of each formal evaluation decision (Credit Evaluation,
    Underwriting, Medical Examination, Final Evaluation) — kept distinct from the plain
    status-transition log so a future Reports/Analytics module (out of scope for 6C) can
    query decisions on their own terms."""

    application_workflow_id: str
    case_type: str
    decision_type: str
    outcome: str
    remarks: str | None = None
    # evaluated_by = created_by, evaluated_at = created_at (BaseDocument fields)
