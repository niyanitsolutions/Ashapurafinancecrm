"""Insurance-only vocabularies for the "Policy Leads" pipeline.

Kept separate from `workflow_engine.constants` (which is shared with Loan) so an
insurance-specific list can change without touching Loan. `InsuranceHoldReason` is the
closed set the Policy Lead "Place On Hold" form offers; `OTHER` unlocks a free-text
`on_hold_other_reason` stored alongside the case's hold information.
"""


class InsurancePaymentStatus:
    """Derived, never client-writable — see `InsuranceCaseDetails.payment_status`.
    `compute` is the single source of truth for the not_paid/partially_paid/fully_paid
    boundary, used both to persist the stored value and to gate Payment -> Policy Issued
    (`InsuranceCaseService.move_to_policy_issued` re-derives it from the stored
    `amount_paid`/`premium_amount` rather than trusting any previously-stored string)."""

    NOT_PAID = "not_paid"
    PARTIALLY_PAID = "partially_paid"
    FULLY_PAID = "fully_paid"

    ALL = (NOT_PAID, PARTIALLY_PAID, FULLY_PAID)

    @staticmethod
    def compute(amount_paid: float, premium_amount: float) -> str:
        if amount_paid <= 0:
            return InsurancePaymentStatus.NOT_PAID
        if amount_paid >= premium_amount:
            return InsurancePaymentStatus.FULLY_PAID
        return InsurancePaymentStatus.PARTIALLY_PAID


class InsuranceHoldReason:
    UNDERWRITING_ISSUES = "underwriting_issues"
    MEDICAL_PENDING = "medical_pending"
    DOCUMENT_NOT_CLEAR = "document_not_clear"
    PAYMENT_PENDING = "payment_pending"
    DOCUMENT_PENDING = "document_pending"
    OTHER = "other"

    ALL = (
        UNDERWRITING_ISSUES,
        MEDICAL_PENDING,
        DOCUMENT_NOT_CLEAR,
        PAYMENT_PENDING,
        DOCUMENT_PENDING,
        OTHER,
    )
