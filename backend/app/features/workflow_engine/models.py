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

    esign_completed: bool = False
    nach_completed: bool = False
    kyc_completed: bool = False

    final_evaluation_remarks: str | None = None

    disbursed_amount: float | None = None
    disbursed_at: datetime | None = None
    disbursed_reference: str | None = None


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

    current_status: str
    rejection_reason: str | None = None  # mandatory whenever current_status == "rejected"

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
