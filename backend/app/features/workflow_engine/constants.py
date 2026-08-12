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

ON_HOLD_STATUS = "on_hold"


class CaseType:
    LOAN = "loan"
    INSURANCE = "insurance"

    ALL = (LOAN, INSURANCE)


class LoanStatus:
    NEW_CUSTOMER = "new_customer"
    DOCUMENTS_PENDING = "documents_pending"
    CREDIT_EVALUATION = "credit_evaluation"
    OFFER_ACCEPTANCE = "offer_acceptance"
    ADDITIONAL_DOCUMENTS = "additional_documents"
    ESIGN_NACH_KYC = "esign_nach_kyc"
    FINAL_EVALUATION = "final_evaluation"
    SEND_FOR_DISBURSEMENT = "send_for_disbursement"
    DISBURSED = "disbursed"
    ON_HOLD = ON_HOLD_STATUS
    REJECTED = "rejected"

    # Every status a case can be resumed back into after being placed on hold.
    RESUMABLE = (
        NEW_CUSTOMER, DOCUMENTS_PENDING, CREDIT_EVALUATION, OFFER_ACCEPTANCE,
        ADDITIONAL_DOCUMENTS, ESIGN_NACH_KYC, FINAL_EVALUATION, SEND_FOR_DISBURSEMENT,
    )
    ALL = (*RESUMABLE, DISBURSED, ON_HOLD, REJECTED)
    TERMINAL = (DISBURSED, REJECTED)


class InsuranceStatus:
    """Finalized lifecycle (decision 064) — supersedes the draft flagged as an
    assumption in decision 057. Both `medical_verification` and `additional_documents`
    are optional, per-case branches decided during Underwriting (and, for additional
    documents, re-checked after Medical Verification clears) — never a fixed product
    attribute. `policy_generation` (staff prepares the policy) and `policy_issued`
    (terminal) are kept as two distinct statuses, not one, per explicit instruction.
    """

    APPLICATION_SUBMITTED = "application_submitted"
    DOCUMENTS_PENDING = "documents_pending"
    UNDERWRITING = "underwriting"
    MEDICAL_VERIFICATION = "medical_verification"
    ADDITIONAL_DOCUMENTS = "additional_documents"
    PREMIUM_ACCEPTANCE = "premium_acceptance"
    POLICY_GENERATION = "policy_generation"
    POLICY_ISSUED = "policy_issued"
    ON_HOLD = ON_HOLD_STATUS
    REJECTED = "rejected"

    RESUMABLE = (
        APPLICATION_SUBMITTED, DOCUMENTS_PENDING, UNDERWRITING, MEDICAL_VERIFICATION,
        ADDITIONAL_DOCUMENTS, PREMIUM_ACCEPTANCE, POLICY_GENERATION,
    )
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
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

    ALL = (PENDING, ACCEPTED, DECLINED)


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
    DOCUMENTS_REQUESTED = "loan_case_documents_requested"
    DOCUMENTS_VERIFIED = "loan_case_documents_verified"
    CREDIT_EVALUATED = "loan_case_credit_evaluated"
    OFFER_ACCEPTED = "loan_case_offer_accepted"
    ADDITIONAL_DOCS_VERIFIED = "loan_case_additional_docs_verified"
    ESIGN_NACH_KYC_COMPLETED = "loan_case_esign_nach_kyc_completed"
    FINAL_EVALUATED = "loan_case_final_evaluated"
    DISBURSED = "loan_case_disbursed"
    REJECTED = "loan_case_rejected"


class InsuranceAuditEvent:
    CASE_CREATED = "insurance_case_created"
    DOCUMENTS_REQUESTED = "insurance_case_documents_requested"
    DOCUMENTS_VERIFIED = "insurance_case_documents_verified"
    MEDICAL_VERIFICATION_REQUIRED = "insurance_case_medical_verification_required"
    ADDITIONAL_DOCUMENTS_REQUIRED = "insurance_case_additional_documents_required"
    PREMIUM_READY = "insurance_case_premium_ready"
    PREMIUM_ACCEPTED = "insurance_case_premium_accepted"
    POLICY_ISSUED = "insurance_case_policy_issued"
    REJECTED = "insurance_case_rejected"
