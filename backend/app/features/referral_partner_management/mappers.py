from app.features.leads.models import Lead
from app.features.referral_partner_management.models import (
    CommissionEntry,
    CommissionRule,
    ReferralPartner,
)
from app.features.referral_partner_management.schemas import (
    CommissionEntryResponse,
    CommissionRuleResponse,
    ReferralLeadResponse,
    ReferralPartnerResponse,
)


def partner_to_response(partner: ReferralPartner) -> ReferralPartnerResponse:
    return ReferralPartnerResponse(
        id=partner.require_id(), partner_code=partner.partner_code, full_name=partner.full_name, mobile=partner.mobile,
        email=partner.email, business_name=partner.business_name, approval_status=partner.approval_status,
        approved_at=partner.approved_at, created_at=partner.created_at, updated_at=partner.updated_at,
    )


def commission_rule_to_response(rule: CommissionRule) -> CommissionRuleResponse:
    return CommissionRuleResponse(
        id=rule.require_id(), label=rule.label, product_category=rule.product_category, partner_id=rule.partner_id,
        calculation_type=rule.calculation_type, rate_or_amount=rule.rate_or_amount, trigger_event=rule.trigger_event,
        status=rule.status, created_at=rule.created_at, updated_at=rule.updated_at,
    )


def commission_entry_to_response(entry: CommissionEntry, partner_name: str | None) -> CommissionEntryResponse:
    return CommissionEntryResponse(
        id=entry.require_id(), partner_id=entry.partner_id, partner_name=partner_name, lead_id=entry.lead_id,
        case_type=entry.case_type, case_id=entry.case_id, rule_id=entry.rule_id, calculation_type=entry.calculation_type,
        rate_or_amount=entry.rate_or_amount, base_amount=entry.base_amount, commission_amount=entry.commission_amount,
        status=entry.status, approved_at=entry.approved_at, paid_at=entry.paid_at, payment_reference=entry.payment_reference,
        created_at=entry.created_at,
    )


def referral_lead_to_response(lead: Lead, external_status: str, editable: bool) -> ReferralLeadResponse:
    return ReferralLeadResponse(
        lead_id=lead.require_id(), lead_code=lead.lead_code, full_name=lead.full_name, mobile=lead.mobile,
        product_category=lead.product_category, product_id=lead.product_id, external_status=external_status,
        editable=editable, submitted_at=lead.created_at,
    )
