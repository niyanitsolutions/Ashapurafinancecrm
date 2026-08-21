"""Module 6A — Lead Foundation constants.

`ProductCategory` is a genuinely fixed set — Loan and Insurance are the two business
lines the whole brief is built around, not a DB-driven concept (unlike `LeadSource`,
which is Module 4's data-driven `lead_sources` catalog). `LeadStatus` deliberately has
exactly one value this round — the real, configurable-per-product-type pipeline
(decision 004) is Module 6C's job; see docs/decisions/DECISIONS.md.

`LeadStage` (decision 125) is a SEPARATE field from `LeadStatus`/`status` — added
alongside it, not a replacement. `status` stays exactly as it was; `stage` is the new
Fresh/My Leads/Document Collection/Rejected pipeline the redesigned Leads UI drives.
"""


class ProductCategory:
    LOAN = "loan"
    INSURANCE = "insurance"

    ALL = (LOAN, INSURANCE)


# The ONLY place a Lead's product category is mapped to the Access Control module that
# gates Lead-assignment eligibility (see LeadService.list_eligible_assignees) — an
# employee is a candidate to receive a lead iff their role holds ANY granted action on
# ANY permission catalog entry under this module (e.g. "loan_management"), the same
# "has module access" concept PermissionEngine.get_accessible_modules already uses for
# nav/menu filtering. Deliberately NOT a `leads:leads:assign` permission check — Owners
# already grant module access (Loan Management / Insurance Management) when setting up a
# role, and should never need to configure a second, separate assignment permission.
# Adding a future product category (e.g. "credit_card") is exactly one line here plus
# creating that module's Permission catalog rows via the existing Roles & Permissions
# UI — the eligibility engine itself never needs to change.
PRODUCT_CATEGORY_MODULE: dict[str, str] = {
    ProductCategory.LOAN: "loan_management",
    ProductCategory.INSURANCE: "insurance_management",
}


class LeadStatus:
    NEW = "new"

    ALL = (NEW,)


class LeadStage:
    """The Leads-redesign pipeline (decision 125) — Fresh Leads -> My Leads ->
    Document Collection, with a Rejected exit reachable from either of the last two.
    `DOCUMENT_COLLECTION` is a real, reachable stage in Phase 1 (My Leads' Stage action
    can move an assigned lead into it) — only its eventual wiring to a real
    Application/ApplicationDocument view is deferred to Phase 3."""

    FRESH = "fresh"
    ASSIGNED = "assigned"  # = "My Leads"
    DOCUMENT_COLLECTION = "document_collection"
    REJECTED = "rejected"
    # Leads workflow redesign Phase 3 (decision 126) — terminal, like REJECTED. Reachable
    # only from DOCUMENT_COLLECTION, gated on the Application being submitted and every
    # required document verified (see LeadService.set_stage). A purely Leads-pipeline
    # bookkeeping label: it never creates, touches, or routes a Loan/Insurance case —
    # that already happened automatically, correctly branched by product_category, when
    # the customer submitted (CustomerService.submit_application, decision #058). An
    # Insurance lead reaching this stage still has (and always had) an Insurance case in
    # Insurance Management, never a Loan Management one.
    LOAN_MANAGEMENT = "loan_management"

    ALL = (FRESH, ASSIGNED, DOCUMENT_COLLECTION, REJECTED, LOAN_MANAGEMENT)


class LeadActivityType:
    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    NOTE_ADDED = "note_added"
    DUPLICATE_DETECTED = "duplicate_detected"
    STAGE_CHANGED = "stage_changed"
    REJECTED = "rejected"
    FOLLOW_UP_SET = "follow_up_set"
    FINANCIAL_ASSESSMENT_UPDATED = "financial_assessment_updated"
    CUSTOMER_ACCOUNT_CREATED = "customer_account_created"
    MOVED_TO_LOAN_MANAGEMENT = "moved_to_loan_management"

    ALL = (
        CREATED, UPDATED, ASSIGNED, UNASSIGNED, NOTE_ADDED, DUPLICATE_DETECTED,
        STAGE_CHANGED, REJECTED, FOLLOW_UP_SET, FINANCIAL_ASSESSMENT_UPDATED, CUSTOMER_ACCOUNT_CREATED,
        MOVED_TO_LOAN_MANAGEMENT,
    )


class SalaryMode:
    """My Leads' Update screen — Salary Mode (spec section 13, Phase 2 / decision 125)."""

    ACCOUNT = "account"
    CASH = "cash"
    CHEQUE = "cheque"

    ALL = (ACCOUNT, CASH, CHEQUE)


class LastThreeMonthsSalary:
    """My Leads' Update screen — Last 3 Months Salary (spec section 13, Phase 2)."""

    SAME = "same"
    HIKED = "hiked"
    DECREASED = "decreased"
    PARTIAL = "partial"

    ALL = (SAME, HIKED, DECREASED, PARTIAL)
