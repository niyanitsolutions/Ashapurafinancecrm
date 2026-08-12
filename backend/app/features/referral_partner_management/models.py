"""Module 7 — Referral Partner Portal domain models.

`Lead` (Module 6A, frozen) is never modified — `ReferralLead` is a separate mapping
collection recording which Lead a Referral Partner submitted, per docs/decisions/
DECISIONS.md. `CommissionEntry` stores a full snapshot of the rule that produced it
(`rule_id` plus the applied `calculation_type`/`rate_or_amount`) and the computed
`commission_amount` itself — calculated once at trigger time and never recomputed, so a
later edit to `CommissionRule` can never silently change historical payouts.
"""

from datetime import datetime

from pydantic import Field

from app.features.referral_partner_management.constants import (
    ApprovalStatus,
    CalculationType,
    CommissionEntryStatus,
    TriggerEvent,
)
from app.shared.base_document import BaseDocument


class ReferralPartner(BaseDocument):
    partner_code: str  # AFS-REF-000001
    user_id: str  # ref: users (Auth) — login identity stays there, same pattern as Customer/Employee

    full_name: str
    mobile: str  # denormalized from users.mobile at creation
    email: str | None = None
    business_name: str | None = None

    approval_status: str = Field(default=ApprovalStatus.PENDING_APPROVAL, pattern=f"^({'|'.join(ApprovalStatus.ALL)})$")
    approved_at: datetime | None = None
    approved_by: str | None = None

    # Reserved, not implemented (per explicit instruction) — a future round could let a
    # Referral Partner have a parent ("Master Referral"), rolling up leads/commission for
    # reporting. Nothing reads or writes this field yet; it exists only so the schema
    # doesn't need a migration to add master/sub-partner relationships later.
    parent_partner_id: str | None = None


class ReferralLead(BaseDocument):
    partner_id: str  # ref: referral_partners
    lead_id: str  # ref: leads (Module 6A, frozen) — the Lead itself is untouched


class CommissionRule(BaseDocument):
    """One collection, Owner-configurable — the scheduler never hardcodes a rate.
    `partner_id=None` means "default rule for this product_category, applies to any
    Referral Partner without a more specific rule of their own"; a rule with `partner_id`
    set overrides the default for that one partner. `status` (inherited) active/inactive
    lets an Owner retire a rule without deleting it — retiring a rule never touches
    `CommissionEntry` rows already created from it (they keep their own snapshot)."""

    label: str
    product_category: str | None = None  # None = applies to all product categories
    partner_id: str | None = None  # None = default rule; set = partner-specific override
    calculation_type: str = Field(pattern=f"^({'|'.join(CalculationType.ALL)})$")
    rate_or_amount: float  # percentage points (e.g. 2.0 = 2%) if percentage, else a flat amount
    trigger_event: str = Field(pattern=f"^({'|'.join(TriggerEvent.ALL)})$")


class CommissionEntry(BaseDocument):
    partner_id: str
    lead_id: str
    case_type: str  # "loan" | "insurance" (workflow_engine.constants.CaseType)
    case_id: str  # ref: application_workflows (Module 6C, frozen, read-only)

    # Snapshot of the rule that produced this entry — never re-read from CommissionRule
    # after creation, so a later rule edit can't change a historical payout.
    rule_id: str
    calculation_type: str
    rate_or_amount: float
    base_amount: float  # the disbursed loan amount / policy premium the calculation was applied to
    commission_amount: float  # calculated once at trigger time, stored, never recomputed

    status: str = Field(default=CommissionEntryStatus.PENDING, pattern=f"^({'|'.join(CommissionEntryStatus.ALL)})$")
    approved_at: datetime | None = None
    approved_by: str | None = None
    paid_at: datetime | None = None
    paid_by: str | None = None
    payment_reference: str | None = None
