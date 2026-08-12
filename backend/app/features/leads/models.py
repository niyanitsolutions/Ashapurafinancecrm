"""Module 6A — Lead Foundation domain models.

A Lead captures raw prospect contact info directly (`full_name`/`mobile`/`email`) —
there's no Customer record to link to yet (Customer Portal connection is Module 6B's
job). `product_id` references either `loan_products` or `insurance_products`
(Module 4) depending on `product_category`; `source_id` references `lead_sources`
(Module 4) — both read-only reuse, no lines changed in `system_settings`.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.features.leads.constants import LeadStatus, ProductCategory
from app.shared.base_document import BaseDocument


class Lead(BaseDocument):
    lead_code: str  # AFS-LEAD-000001, auto-generated

    full_name: str
    mobile: str
    email: str | None = None

    # Set once the customer authenticates against a Secure Application Link for this
    # lead — `user_id`/`account_created`/`account_created_at` at claim time (see
    # CustomerService.claim_secure_link), `customer_id` once profile completion creates
    # the Customer record (see CustomerService.complete_profile). All four default to
    # "not yet" so every Lead created before this existed is unaffected.
    customer_id: str | None = None
    user_id: str | None = None
    account_created: bool = False
    account_created_at: datetime | None = None

    source_id: str  # ref: system_settings.lead_sources
    product_category: str = Field(pattern=f"^({'|'.join(ProductCategory.ALL)})$")
    product_id: str  # ref: system_settings.loan_products or .insurance_products, per product_category

    remarks: str | None = None
    city: str | None = None
    preferred_amount: float | None = None
    assigned_to: str | None = None  # ref: employees (Module 2), nullable — unassigned until set

    # Product Schema Engine (additive, optional — see docs/decisions/DECISIONS.md #051
    # amendment): when the selected product has an `ApplicationFormDefinition`, Create
    # Lead can render its Basic Information fields and capture answers here. Both null
    # for a Lead created before this existed, or for a product with no schema yet — the
    # rest of the Lead flow is unaffected either way.
    form_definition_id: str | None = None
    product_form_data: dict[str, Any] | None = None

    # Recorded at creation time via a mobile-number lookup against existing leads — never
    # blocks creation, just flags for staff review (decision — see docs/decisions/DECISIONS.md).
    duplicate_of_lead_ids: list[str] = Field(default_factory=list)

    # Overrides BaseDocument.status's generic "active" default — only one value exists
    # this round (see constants.py docstring); the real pipeline is Module 6C's job.
    status: str = Field(default=LeadStatus.NEW, pattern=f"^({'|'.join(LeadStatus.ALL)})$")


class LeadNote(BaseDocument):
    lead_id: str
    text: str
    # created_by = author, created_at = when (BaseDocument fields, not duplicated here)


class LeadActivity(BaseDocument):
    lead_id: str
    event_type: str = Field(pattern=r"^[a-z_]+$")
    metadata: dict[str, Any] | None = None
    # created_by = actor, created_at = when (BaseDocument fields, not duplicated here)
