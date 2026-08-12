"""Module 7 — Referral Partner Portal constants.

Per the approved design (docs/decisions/DECISIONS.md #075+): a Referral Partner is a
brand new external actor with its own approval gate and commission ledger, built without
touching any frozen module. Commission Rules are Owner-configurable data (never a
hardcoded rate), mirroring the "engine is code, catalog is data" split already used for
Access Control's `PermissionEngine`, 6C's `WorkflowEngine`, and 6D's Reminder Rules.
"""


class ApprovalStatus:
    """A Referral Partner's `User` account can be fully active (password set, can log
    in) while still `pending_approval` here — login and portal-action authorization are
    deliberately two separate gates. Only `active` partners may submit leads."""

    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"

    ALL = (PENDING_APPROVAL, ACTIVE, DEACTIVATED)


class CalculationType:
    PERCENTAGE = "percentage"
    FLAT = "flat"

    ALL = (PERCENTAGE, FLAT)


class TriggerEvent:
    """The case-lifecycle event a Commission Rule pays out on. Matches 6C's own terminal
    "success" statuses — decision 064's `LoanStatus.DISBURSED` / `InsuranceStatus.
    POLICY_ISSUED` — never any other status, since only a completed, successful case
    generates a payable commission."""

    LOAN_DISBURSED = "loan_disbursed"
    INSURANCE_POLICY_ISSUED = "insurance_policy_issued"

    ALL = (LOAN_DISBURSED, INSURANCE_POLICY_ISSUED)


class CommissionEntryStatus:
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"

    ALL = (PENDING, APPROVED, PAID)


class ExternalLeadStatus:
    """The only vocabulary a Referral Partner ever sees for their own submitted leads —
    never a raw internal Lead/Application/Case status (Credit Evaluation, Underwriting,
    NACH, KYC, ...). Computed by `_external_status_for_lead`, not stored — see
    docs/decisions/DECISIONS.md."""

    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"

    ALL = (SUBMITTED, IN_PROGRESS, APPROVED, REJECTED)


class AuditEvent:
    PARTNER_CREATED = "referral_partner_created"
    PARTNER_APPROVED = "referral_partner_approved"
    PARTNER_DEACTIVATED = "referral_partner_deactivated"
    REFERRAL_LEAD_ADDED = "referral_lead_added"
    COMMISSION_RULE_CREATED = "commission_rule_created"
    COMMISSION_RULE_UPDATED = "commission_rule_updated"
    COMMISSION_ENTRY_CREATED = "commission_entry_created"
    COMMISSION_ENTRY_APPROVED = "commission_entry_approved"
    COMMISSION_ENTRY_PAID = "commission_entry_paid"


# The Lead Source (Module 4, seeded since 6A) every referral-submitted Lead is recorded
# under — never caller-supplied, so a Referral Partner can't misattribute a lead's source.
REFERRAL_LEAD_SOURCE_NAME = "Referral"
