"""Loan-only domain models (decision #129). `ApplicationWorkflow`/`LoanCaseDetails` stay
in `workflow_engine` since they're shared with Insurance — a bank/NBFC offer has no
Insurance equivalent, so it belongs in this product module instead, not the shared engine.
"""

from datetime import datetime

from pydantic import Field

from app.features.workflow_engine.constants import BankOfferDecision
from app.shared.base_document import BaseDocument


class LoanCaseBankOffer(BaseDocument):
    """One bank/NBFC's offer against a Loan Case. A case can have any number of these —
    adding one never overwrites another (contrast with the old, single-slot
    `LoanCaseDetails.bank_nbfc_name`/`bank_decision`/etc. fields this supersedes for new
    cases, decision #129/superseding #061). `is_selected` marks the one offer, if any,
    the case has actually moved forward with — enforced at the service layer (only one
    `True` per `loan_case_id` at a time, never at the schema level).

    Production redesign (this round): now created starting at `new_customer` (previously
    `credit_evaluation` only), so the SAME record carries a bank/NBFC from the Staff's
    initial intake all the way through the Credit Evaluation decision — never a second,
    duplicate capture. `branch`/`loan_type`/`requested_amount` are the New Customer-stage
    fields (superseding `LoanCaseDetails.preferred_branch`/`loan_type`/`requested_amount`
    for new cases, same way `bank_name` already superseded `preferred_bank_name`);
    `emi_per_month` is the new Credit Evaluation decision field, sibling to
    `processing_fee`."""

    loan_case_id: str

    bank_name: str  # free text — no Bank/NBFC master table exists in this codebase
    branch: str | None = None
    loan_type: str | None = None
    requested_amount: float | None = None
    bank_application_id: str | None = None
    reference_number: str | None = None
    assigned_officer: str | None = None

    # PENDING until a staff member records a real decision at Credit Evaluation — an
    # offer captured at New Customer starts here.
    decision: str = Field(default=BankOfferDecision.PENDING, pattern=f"^({'|'.join(BankOfferDecision.ALL)})$")
    # Required (enforced at the schema/service layer, not here) iff decision == APPROVED;
    # always None otherwise.
    approved_amount: float | None = None
    interest_rate: float | None = None
    tenure_months: int | None = None
    processing_fee: float | None = None
    emi_per_month: float | None = None
    remarks: str | None = None

    is_selected: bool = False
    selected_at: datetime | None = None
    selected_by: str | None = None  # User id — a customer or staff member can select


class LoanCaseAdditionalDocument(BaseDocument):
    """One ad-hoc, staff-named document requested at the `additional_documents` stage —
    deliberately NOT another row in the fixed `document_type_id` catalog
    (`ApplicationDocument`/`RequiredDocumentDefinition`, Module 6B): that catalog is
    shared master data, while this is a free-text name a staff member types for one
    specific case (e.g. "Salary Revision Letter"). Reuses the same S3
    presigned-URL storage primitive as every other document in this project
    (`app/services/storage/client.py`) — this model is only the metadata row sitting on
    top of it, not a second storage mechanism. `created_by`/`created_at` (from
    `BaseDocument`) double as who requested it and when."""

    loan_case_id: str
    application_id: str
    name: str

    document_status: str = "requested"  # "requested" | "uploaded" — mirrors
    # `DocumentAvailabilityStatus`'s two-state pattern in Module 6B.
    verification_status: str = "pending"  # "pending" | "verified" | "rejected"
    rejection_reason: str | None = None

    s3_key: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    uploaded_at: datetime | None = None

    verified_by: str | None = None
    verified_at: datetime | None = None
