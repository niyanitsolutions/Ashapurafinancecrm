"""Insurance-only vocabularies for the "Policy Leads" pipeline.

Kept separate from `workflow_engine.constants` (which is shared with Loan) so an
insurance-specific list can change without touching Loan. `InsuranceHoldReason` is the
closed set the Policy Lead "Place On Hold" form offers; `OTHER` unlocks a free-text
`on_hold_other_reason` stored alongside the case's hold information.
"""


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
