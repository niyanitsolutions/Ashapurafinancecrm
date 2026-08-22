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
    `True` per `loan_case_id` at a time, never at the schema level)."""

    loan_case_id: str

    bank_name: str  # free text — no Bank/NBFC master table exists in this codebase
    bank_application_id: str | None = None
    reference_number: str | None = None
    assigned_officer: str | None = None

    decision: str = Field(pattern=f"^({'|'.join(BankOfferDecision.ALL)})$")
    # Required (enforced at the schema/service layer, not here) iff decision == APPROVED;
    # always None otherwise.
    approved_amount: float | None = None
    remarks: str | None = None

    is_selected: bool = False
    selected_at: datetime | None = None
    selected_by: str | None = None  # User id — a customer or staff member can select
