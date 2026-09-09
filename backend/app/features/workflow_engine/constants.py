"""Module 6C — status vocabularies for the two processing pipelines this engine drives.

Per the approved Workflow Proposal (docs/MODULE_6C_WORKFLOW_PROPOSAL.md) and the two
follow-up business reviews: rejection is reachable from two points on each pipeline, no
status supports rollback in this first version (`WorkflowDefinition.
allowed_previous_statuses` exists on the schema for future use but is always empty), and
— per the final pre-freeze refinement — every non-terminal status on both pipelines also
allows a transition to the shared `on_hold` status, with `resume` returning the case to
whichever status it was in before (see `workflow_engine/hold.py`). Insurance's lifecycle
was finalized in that same round (decision 064), superseding the draft flagged as an
assumption in decision 057.
"""

from typing import ClassVar

ON_HOLD_STATUS = "on_hold"


class CaseType:
    LOAN = "loan"
    INSURANCE = "insurance"

    ALL = (LOAN, INSURANCE)


class LoanStatus:
    """Production redesign (decision #129): `DOCUMENTS_PENDING` is kept defined — old
    `ApplicationStatusHistory` rows reference it as a plain string and the model layer
    doesn't constrain `current_status`, so removing the constant would be a needless
    break — but it is deliberately absent from `RESUMABLE`/`ALL` below: no new case can
    ever be placed into it again. Document Collection is a Leads-module concept
    (`LeadStage.DOCUMENT_COLLECTION`), not a Loan Management stage — a Lead only reaches
    Loan Management after its required documents are already verified (Leads decision
    #127). `request_documents`/`verify_documents` remain available as optional,
    non-pipeline-driving actions at `NEW_CUSTOMER`/`ADDITIONAL_DOCUMENTS`."""

    NEW_CUSTOMER = "new_customer"
    DOCUMENTS_PENDING = "documents_pending"  # retired from ALL/RESUMABLE — see docstring
    CREDIT_EVALUATION = "credit_evaluation"
    OFFER_ACCEPTANCE = "offer_acceptance"
    ADDITIONAL_DOCUMENTS = "additional_documents"
    RV_OV_REF = "rv_ov_ref"
    ESIGN_NACH_KYC = "esign_nach_kyc"
    FINAL_EVALUATION = "final_evaluation"
    SEND_FOR_DISBURSEMENT = "send_for_disbursement"
    DISBURSED = "disbursed"
    ON_HOLD = ON_HOLD_STATUS
    RE_ELIGIBLE = "re_eligible"
    REJECTED = "rejected"

    # Every status a case can be resumed back into after being placed on hold.
    RESUMABLE = (
        NEW_CUSTOMER, CREDIT_EVALUATION, OFFER_ACCEPTANCE, ADDITIONAL_DOCUMENTS,
        RV_OV_REF, ESIGN_NACH_KYC, FINAL_EVALUATION, SEND_FOR_DISBURSEMENT, RE_ELIGIBLE,
    )
    ALL = (*RESUMABLE, DISBURSED, ON_HOLD, REJECTED)
    # `RE_ELIGIBLE` is deliberately NOT terminal (a case can move back to
    # `CREDIT_EVALUATION`); `REJECTED` stays terminal — `list_eligible_assignees`
    # (leads/service.py) relies on TERMINAL meaning "permanently closed, doesn't count
    # against workload," and letting a rejected case silently reopen would break that.
    TERMINAL = (DISBURSED, REJECTED)


class TopUpPeriod:
    """Top Up Loan eligibility scheduling (production add-on to the Disbursed stage —
    NOT a `LoanStatus` member: a Top Up decision never transitions `current_status`, it
    only sets `LoanCaseDetails.top_up_*` fields on an otherwise-unchanged `disbursed`
    case; see `LoanCaseService.schedule_top_up`). `THREE_MONTHS`/`SIX_MONTHS`/
    `TWELVE_MONTHS` are CALENDAR months from `disbursed_at` (see `app.utils.datetime.
    add_calendar_months`), never a fixed day-count. `NO` schedules nothing (the case
    stays plain `disbursed`, never Top Up eligible). `CUSTOM` uses a staff-supplied date
    (validated >= `disbursed_at`) instead of a period."""

    THREE_MONTHS = "3_months"
    SIX_MONTHS = "6_months"
    TWELVE_MONTHS = "12_months"
    NO = "no"
    CUSTOM = "custom"

    ALL = (THREE_MONTHS, SIX_MONTHS, TWELVE_MONTHS, NO, CUSTOM)
    # Only these three carry a fixed calendar-month offset; NO/CUSTOM compute their
    # eligibility date differently (see schedule_top_up).
    MONTHS_BY_PERIOD = {THREE_MONTHS: 3, SIX_MONTHS: 6, TWELVE_MONTHS: 12}


class ReEligibilityPeriod:
    """Reject → Re-Eligibility scheduling (production add-on to every Loan Management
    stage that can Reject). Mirrors `TopUpPeriod`'s shape: `THREE/SIX/NINE/TWELVE_MONTHS`
    are CALENDAR months from the rejection instant (`app.utils.datetime.
    add_calendar_months`); `CUSTOM` uses a staff-supplied future date; `NO` is an
    explicit "never automatically become Re-Eligible" — NOT a default duration. A `NO`
    (or unscheduled) rejected case has `re_eligible_date is None` and the auto-transition
    worker job never touches it."""

    THREE_MONTHS = "3_months"
    SIX_MONTHS = "6_months"
    NINE_MONTHS = "9_months"
    TWELVE_MONTHS = "12_months"
    CUSTOM = "custom"
    NO = "no"

    ALL = (THREE_MONTHS, SIX_MONTHS, NINE_MONTHS, TWELVE_MONTHS, CUSTOM, NO)
    MONTHS_BY_PERIOD: ClassVar[dict[str, int]] = {THREE_MONTHS: 3, SIX_MONTHS: 6, NINE_MONTHS: 9, TWELVE_MONTHS: 12}


class InsuranceStatus:
    """Insurance "Policy Leads" redesign (2026-09-07) — a FULL REPLACE of the
    decision-064 lifecycle, superseding it. The new pipeline is
    `fresh_lead -> policy_document -> policy_login -> policy_issued`, with `rejected`
    reachable from any non-terminal stage and `re_eligible` reachable from `rejected`
    (auto-scheduled at rejection time or a manual "Mark Re-Eligible"), and `on_hold`
    from every non-terminal stage. The old
    `underwriting`/`medical_verification`/`additional_documents`/`premium_acceptance`/
    `policy_generation` statuses are gone; live cases were remapped by
    `scripts/migrate_redesign_insurance_pipeline.py`
    (documents_pending|underwriting|medical_verification|additional_documents ->
    policy_document; premium_acceptance|policy_generation -> policy_login).

    "Move Back" is wired for insurance too (`policy_login -> policy_document`,
    `policy_document -> fresh_lead`) via `WorkflowDefinition.allowed_previous_statuses`.
    """

    FRESH_LEAD = "fresh_lead"
    POLICY_DOCUMENT = "policy_document"
    POLICY_LOGIN = "policy_login"
    POLICY_ISSUED = "policy_issued"
    RE_ELIGIBLE = "re_eligible"
    ON_HOLD = ON_HOLD_STATUS
    REJECTED = "rejected"

    # `re_eligible` is resumable (it can be placed on hold) and deliberately NOT terminal
    # — a re-eligible case restarts from `fresh_lead`/`policy_document`. `rejected` stays
    # terminal (see `TERMINAL_STATUSES_BY_CASE_TYPE`'s consumers).
    RESUMABLE = (FRESH_LEAD, POLICY_DOCUMENT, POLICY_LOGIN, RE_ELIGIBLE)
    ALL = (*RESUMABLE, POLICY_ISSUED, ON_HOLD, REJECTED)
    TERMINAL = (POLICY_ISSUED, REJECTED)


# The one place a case_type maps to its own pipeline's terminal statuses — lets a caller
# (e.g. LeadService.list_eligible_assignees, computing "open case" workload per
# employee) ask "is this case still open?" without branching on "loan" vs "insurance"
# itself. A future case_type just adds an entry here.
TERMINAL_STATUSES_BY_CASE_TYPE: dict[str, tuple[str, ...]] = {
    CaseType.LOAN: LoanStatus.TERMINAL,
    CaseType.INSURANCE: InsuranceStatus.TERMINAL,
}


class DecisionType:
    CREDIT_EVALUATION = "credit_evaluation"
    UNDERWRITING = "underwriting"
    MEDICAL_VERIFICATION = "medical_verification"
    FINAL_EVALUATION = "final_evaluation"

    ALL = (CREDIT_EVALUATION, UNDERWRITING, MEDICAL_VERIFICATION, FINAL_EVALUATION)


class DecisionOutcome:
    APPROVED = "approved"
    REJECTED = "rejected"
    CLEARED = "cleared"  # medical verification only
    FAILED = "failed"  # medical verification only

    ALL = (APPROVED, REJECTED, CLEARED, FAILED)


class OfferDecision:
    """Still used by `insurance_management` for `premium_decision` — the Loan pipeline no
    longer uses this (superseded by `BankOfferDecision` on `LoanCaseBankOffer`, decision
    #129, replacing the single-offer `record_offer`/`accept_offer`/`decline_offer` flow
    decision #062 documented as unused by any frontend)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

    ALL = (PENDING, ACCEPTED, DECLINED)


class BankOfferDecision:
    """Per-bank decision on a `LoanCaseBankOffer` — deliberately independent of the Loan
    Case's own `current_status` (decision #129): a case can sit in `credit_evaluation`
    with several banks already decided (some approved, some not) while staff/customer
    haven't yet selected a final offer. `PENDING` is the default for an offer captured at
    `new_customer`, before any bank decision has been recorded — a case can now carry
    bank/NBFC records from the New Customer stage onward, not only from Credit
    Evaluation."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED_RE_ELIGIBLE = "rejected_re_eligible"

    ALL = (PENDING, APPROVED, REJECTED_RE_ELIGIBLE)


class HoldReason:
    """Closed vocabulary for placing a case `on_hold` — an Optional Status on both
    pipelines' `WorkflowDefinition` rows, not a hardcoded branch in engine code (per
    explicit instruction). Distinct from `rejected`: a hold is always expected to
    `resume`, not end the case."""

    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    WAITING_FOR_BANK = "waiting_for_bank"
    WAITING_FOR_INSURANCE_COMPANY = "waiting_for_insurance_company"
    INTERNAL_REVIEW = "internal_review"
    DOCUMENT_CLARIFICATION = "document_clarification"

    ALL = (WAITING_FOR_CUSTOMER, WAITING_FOR_BANK, WAITING_FOR_INSURANCE_COMPANY, INTERNAL_REVIEW, DOCUMENT_CLARIFICATION)


class WorkflowAuditEvent:
    CASE_CREATED = "workflow_case_created"
    STATUS_CHANGED = "workflow_status_changed"
    CASE_ASSIGNED = "workflow_case_assigned"
    CASE_REASSIGNED = "workflow_case_reassigned"
    DOCUMENTS_REQUESTED = "workflow_documents_requested"
    NOTE_ADDED = "workflow_note_added"
    CASE_ON_HOLD = "workflow_case_on_hold"
    CASE_RESUMED = "workflow_case_resumed"


class LoanAuditEvent:
    """`WorkflowDefinition.audit_event` values for the Loan pipeline — each describes
    what happened to enter that status (see docs/MODULE_6C_WORKFLOW_PROPOSAL.md)."""

    CASE_CREATED = "loan_case_created"
    NEW_CUSTOMER_DETAILS_RECORDED = "loan_case_new_customer_details_recorded"
    DOCUMENTS_REQUESTED = "loan_case_documents_requested"
    DOCUMENTS_VERIFIED = "loan_case_documents_verified"
    CREDIT_EVALUATED = "loan_case_credit_evaluated"
    BANK_OFFER_ADDED = "loan_case_bank_offer_added"
    BANK_OFFER_SELECTED = "loan_case_bank_offer_selected"
    OFFER_ACCEPTED = "loan_case_offer_accepted"
    ADDITIONAL_DOCS_VERIFIED = "loan_case_additional_docs_verified"
    RV_OV_REF_COMPLETED = "loan_case_rv_ov_ref_completed"
    ESIGN_NACH_KYC_COMPLETED = "loan_case_esign_nach_kyc_completed"
    FINAL_EVALUATED = "loan_case_final_evaluated"
    DISBURSED = "loan_case_disbursed"
    REJECTED = "loan_case_rejected"
    MARKED_RE_ELIGIBLE = "loan_case_marked_re_eligible"
    RE_ELIGIBILITY_SCHEDULED = "loan_case_re_eligibility_scheduled"
    RE_ELIGIBILITY_AUTO_TRANSITIONED = "loan_case_re_eligibility_auto_transitioned"
    MOVED_TO_LOAN_MANAGEMENT = "loan_case_moved_to_loan_management"
    TOP_UP_SCHEDULED = "loan_case_top_up_scheduled"
    TOP_UP_MOVED_TO_DOCUMENT_COLLECTION = "loan_case_top_up_moved_to_document_collection"
    # Deliberate administrative "Staff Override — Skip Stage Validations" stage move.
    STAFF_OVERRIDE_STAGE_MOVE = "loan_case_staff_override_stage_move"


class InsuranceAuditEvent:
    # Kept for historical audit_logs rows; the retired ones are no longer emitted.
    CASE_CREATED = "insurance_case_created"
    DOCUMENTS_REQUESTED = "insurance_case_documents_requested"
    DOCUMENTS_VERIFIED = "insurance_case_documents_verified"
    MEDICAL_VERIFICATION_REQUIRED = "insurance_case_medical_verification_required"
    ADDITIONAL_DOCUMENTS_REQUIRED = "insurance_case_additional_documents_required"
    PREMIUM_READY = "insurance_case_premium_ready"
    PREMIUM_ACCEPTED = "insurance_case_premium_accepted"
    POLICY_ISSUED = "insurance_case_policy_issued"
    REJECTED = "insurance_case_rejected"

    # Policy Leads redesign (2026-09-07).
    POLICY_DOCUMENT_STARTED = "insurance_case_policy_document_started"
    POLICY_LOGIN_STARTED = "insurance_case_policy_login_started"
    MOVED_BACK = "insurance_case_moved_back"
    POLICY_LOGIN_UPDATED = "insurance_case_policy_login_updated"
    PRODUCT_CHANGED = "insurance_case_product_changed"
    MARKED_RE_ELIGIBLE = "insurance_case_marked_re_eligible"
    RE_ELIGIBILITY_SCHEDULED = "insurance_case_re_eligibility_scheduled"
    RE_ELIGIBILITY_AUTO_TRANSITIONED = "insurance_case_re_eligibility_auto_transitioned"

    # Phase 5 — ad-hoc "Add Other Document" (per-case, never a Product Schema change).
    ADDITIONAL_DOCUMENT_REQUESTED = "insurance_case_additional_document_requested"

    # Manual lead creation + staff "Move To" stage movement.
    MANUAL_CASE_CREATED = "insurance_case_manual_created"
    STAGE_MOVED = "insurance_case_stage_moved"
