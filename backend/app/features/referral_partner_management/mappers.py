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
        kyc_status=partner.kyc_status, account_active=partner.account_active, submission_mode=partner.submission_mode,
        id=partner.require_id(), partner_code=partner.partner_code, full_name=partner.full_name, mobile=partner.mobile,
        email=partner.email, business_name=partner.business_name, approval_status=partner.approval_status,
        approved_at=partner.approved_at, created_at=partner.created_at, updated_at=partner.updated_at,
    )


def commission_rule_to_response(rule: CommissionRule) -> CommissionRuleResponse:
    return CommissionRuleResponse(
        previous_rule_id=rule.previous_rule_id, fixed_contract_confirmed=rule.fixed_contract_confirmed, fixed_event_policy=rule.fixed_event_policy, product_id=rule.product_id, effective_from=rule.effective_from, effective_until=rule.effective_until, rule_version=rule.rule_version, terms=rule.terms,
        id=rule.require_id(), label=rule.label, product_category=rule.product_category, partner_id=rule.partner_id,
        calculation_type=rule.calculation_type, rate_or_amount=rule.rate_or_amount, trigger_event=rule.trigger_event,
        status=rule.status, created_at=rule.created_at, updated_at=rule.updated_at,
    )


def commission_entry_to_response(entry: CommissionEntry, partner_name: str | None) -> CommissionEntryResponse:
    return CommissionEntryResponse(
        approved_amount=entry.approved_amount, reserved_amount=entry.reserved_amount, additional_earned_amount=entry.additional_earned_amount, total_earned_amount=entry.commission_amount + entry.additional_earned_amount, disbursement_event_source=entry.disbursement_event_source,
        version=entry.version, adjusted_amount=entry.adjusted_amount, recovery_due_amount=entry.recovery_due_amount, application_id=entry.application_id, disbursement_event_id=entry.disbursement_event_id, paid_amount=entry.paid_amount or (entry.commission_amount + entry.additional_earned_amount + entry.adjusted_amount if entry.status == "paid" else 0), outstanding_amount=0 if entry.status == "paid" else (entry.outstanding_amount if entry.outstanding_amount is not None else entry.commission_amount + entry.additional_earned_amount + entry.adjusted_amount - entry.paid_amount), rule_version=entry.rule_version,
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
