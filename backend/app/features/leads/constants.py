"""Module 6A — Lead Foundation constants.

`ProductCategory` is a genuinely fixed set — Loan and Insurance are the two business
lines the whole brief is built around, not a DB-driven concept (unlike `LeadSource`,
which is Module 4's data-driven `lead_sources` catalog). `LeadStatus` deliberately has
exactly one value this round — the real, configurable-per-product-type pipeline
(decision 004) is Module 6C's job; see docs/decisions/DECISIONS.md.
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


class LeadActivityType:
    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    NOTE_ADDED = "note_added"
    DUPLICATE_DETECTED = "duplicate_detected"

    ALL = (CREATED, UPDATED, ASSIGNED, UNASSIGNED, NOTE_ADDED, DUPLICATE_DETECTED)
