"""Module 7 — Referral Partner Portal business logic.

Reuses, unmodified: Auth's `AuthService.send_otp` (decisions 003/011's own invite
mechanism — a Referral Partner's `User` account and OTP invite are created by *calling*
that existing method, not reimplementing it) and Leads' `LeadService.create_lead`/
`update_lead` (Module 6A, frozen — a Referral Partner's "Add Lead"/edit-own-lead actions
are the exact same service calls Owner/Employee use, just invoked with the Referral
Partner's own `User` as actor). `Lead`'s own schema is never modified — `ReferralLead` is
a separate mapping collection, and external status is computed on read, never stored.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants.roles import REFERRAL_PARTNER as REFERRAL_PARTNER_ROLE
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.auth.service import AuthService
from app.features.customer.repository import ApplicationRepository
from app.features.leads.models import Lead
from app.features.leads.repository import LeadRepository
from app.features.leads.schemas import CreateLeadRequest, UpdateLeadRequest
from app.features.leads.service import LeadService
from app.features.referral_partner_management.constants import (
    REFERRAL_LEAD_SOURCE_NAME,
    ApprovalStatus,
    AuditEvent,
    CalculationType,
    CommissionEntryStatus,
    ExternalLeadStatus,
    TriggerEvent,
)
from app.features.referral_partner_management.mappers import referral_lead_to_response
from app.features.referral_partner_management.models import (
    CommissionEntry,
    CommissionRule,
    ReferralLead,
    ReferralPartner,
)
from app.features.referral_partner_management.repository import (
    CommissionEntryRepository,
    CommissionRuleRepository,
    ReferralLeadRepository,
    ReferralPartnerRepository,
)
from app.features.referral_partner_management.schemas import (
    AddReferralLeadRequest,
    CreateCommissionRuleRequest,
    CreateReferralPartnerRequest,
    ReferralDashboardResponse,
    SettleCommissionEntryRequest,
    UpdateCommissionRuleRequest,
    UpdateReferralLeadRequest,
)
from app.features.system_settings.models import InsuranceProduct, LoanProduct
from app.features.system_settings.repository import InsuranceProductRepository, LeadSourceRepository, LoanProductRepository
from app.features.workflow_engine.constants import CaseType, InsuranceStatus, LoanStatus
from app.features.workflow_engine.repository import ApplicationWorkflowRepository
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.id_generator import IdPrefix, generate_id


class ReferralPartnerManagementService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis | None = None) -> None:
        # `redis` is only needed by `create_partner` (it invites via Auth's own OTP
        # flow) — every other method, including the worker-driven commission-entry
        # creation path, never touches it. Kept optional rather than always
        # constructing `AuthService` eagerly, so the scheduled job (which has no Redis
        # client of its own reason to construct) doesn't need a throwaway one.
        self._db = db
        self._redis = redis
        self._partners = ReferralPartnerRepository(db)
        self._referral_leads = ReferralLeadRepository(db)
        self._rules = CommissionRuleRepository(db)
        self._entries = CommissionEntryRepository(db)
        self._users = UserRepository(db)
        self._leads = LeadRepository(db)
        self._applications = ApplicationRepository(db)
        self._workflows = ApplicationWorkflowRepository(db)
        self._lead_sources = LeadSourceRepository(db)
        self._loan_products = LoanProductRepository(db)
        self._insurance_products = InsuranceProductRepository(db)
        self._lead_service = LeadService(db)

    # ================================================================== Owner: partner lifecycle

    async def create_partner(self, payload: CreateReferralPartnerRequest, actor: User) -> ReferralPartner:
        assert self._redis is not None  # only the real HTTP-driven path (which has a Redis client) reaches here
        auth = AuthService(self._db, self._redis)
        await auth.send_otp(mobile=payload.mobile, role=REFERRAL_PARTNER_ROLE, inviter=actor)
        user = await self._users.find_by_mobile(payload.mobile)
        assert user is not None  # send_otp just created (or resent to) this exact mobile/role

        partner_code = await generate_id(self._db, IdPrefix.REFERRAL_PARTNER)
        partner = ReferralPartner(
            partner_code=partner_code, user_id=user.require_id(), full_name=payload.full_name, mobile=payload.mobile,
            email=payload.email, business_name=payload.business_name, created_by=actor.require_id(),
        )
        partner_id = await self._partners.insert(partner)
        await write_audit_log(self._db, event_type=AuditEvent.PARTNER_CREATED, user_id=actor.require_id(), metadata={"partner_id": partner_id})
        found = await self._partners.find_by_id(partner_id)
        assert found is not None
        return found

    async def approve_partner(self, partner_id: str, actor: User) -> ReferralPartner:
        partner = await self.get_partner(partner_id)
        if partner.approval_status == ApprovalStatus.ACTIVE:
            raise ValidationError("This Referral Partner is already active.")
        updated = await self._partners.update(
            partner_id, {"approval_status": ApprovalStatus.ACTIVE, "approved_at": utc_now(), "approved_by": actor.require_id()}, updated_by=actor.require_id()
        )
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.PARTNER_APPROVED, user_id=actor.require_id(), metadata={"partner_id": partner_id})
        return updated

    async def deactivate_partner(self, partner_id: str, actor: User) -> ReferralPartner:
        await self.get_partner(partner_id)
        updated = await self._partners.update(partner_id, {"approval_status": ApprovalStatus.DEACTIVATED}, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.PARTNER_DEACTIVATED, user_id=actor.require_id(), metadata={"partner_id": partner_id})
        return updated

    async def list_partners(
        self, *, search: str | None, approval_status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[ReferralPartner], int]:
        return await self._partners.search_and_filter(search=search, approval_status=approval_status, skip=skip, limit=limit, sort=sort)

    async def get_partner(self, partner_id: str) -> ReferralPartner:
        partner = await self._partners.find_by_id(partner_id)
        if partner is None:
            raise NotFoundError("Referral Partner not found.")
        return partner

    # ================================================================== Referral Partner: self-service

    async def get_own_partner(self, actor: User) -> ReferralPartner:
        partner = await self._partners.find_by_user_id(actor.require_id())
        if partner is None:
            raise NotFoundError("Referral Partner profile not found.")
        return partner

    async def _require_active_partner(self, actor: User) -> ReferralPartner:
        partner = await self.get_own_partner(actor)
        if partner.approval_status != ApprovalStatus.ACTIVE:
            raise ForbiddenError("Your Referral Partner account is not yet approved by the Owner.")
        return partner

    async def list_products(self, category: str) -> list[LoanProduct] | list[InsuranceProduct]:
        """Read-only product picker for the Referral Partner's own Add Lead form — a
        Referral Partner has no `system_settings` permission grant (see
        PermissionEngine.has_permission, Owner/Employee only), so this is a dedicated,
        self-service-scoped read rather than reusing the staff `/loan-products` /
        `/insurance-products` endpoints directly."""
        if category not in ("loan", "insurance"):
            raise ValidationError("category must be 'loan' or 'insurance'.")
        repo = self._loan_products if category == "loan" else self._insurance_products
        return await repo.find_many({}, limit=200)

    async def add_lead(self, payload: AddReferralLeadRequest, actor: User) -> tuple[Lead, ReferralLead]:
        partner = await self._require_active_partner(actor)
        source = await self._lead_sources.find_by_name(REFERRAL_LEAD_SOURCE_NAME)
        if source is None:
            raise ValidationError("The 'Referral' lead source is not configured.")

        lead = await self._lead_service.create_lead(
            CreateLeadRequest(
                full_name=payload.full_name, mobile=payload.mobile, email=payload.email, source_id=source.require_id(),
                product_category=payload.product_category, product_id=payload.product_id, remarks=payload.remarks,
                product_form_data=payload.product_form_data,
            ),
            actor,
        )
        referral_lead = ReferralLead(partner_id=partner.require_id(), lead_id=lead.require_id(), created_by=actor.require_id())
        await self._referral_leads.insert(referral_lead)
        await write_audit_log(
            self._db, event_type=AuditEvent.REFERRAL_LEAD_ADDED, user_id=actor.require_id(),
            metadata={"partner_id": partner.require_id(), "lead_id": lead.require_id()},
        )
        return lead, referral_lead

    async def update_own_lead(self, lead_id: str, payload: UpdateReferralLeadRequest, actor: User) -> Lead:
        partner = await self._require_active_partner(actor)
        mapping = await self._referral_leads.find_by_lead_id(lead_id)
        if mapping is None or mapping.partner_id != partner.require_id():
            raise NotFoundError("Lead not found.")
        lead = await self._leads.find_by_id(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        _status, editable = await self.external_status_and_editable(lead)
        if not editable:
            raise ForbiddenError("This lead can no longer be edited — processing has already started.")
        return await self._lead_service.update_lead(
            lead_id, UpdateLeadRequest(full_name=payload.full_name, mobile=payload.mobile, email=payload.email, remarks=payload.remarks), actor
        )

    async def list_own_leads(self, actor: User, *, skip: int, limit: int) -> tuple[list[tuple[Lead, str, bool]], int]:
        partner = await self.get_own_partner(actor)
        mappings, total = await self._referral_leads.find_for_partner(partner.require_id(), skip=skip, limit=limit)
        results: list[tuple[Lead, str, bool]] = []
        for mapping in mappings:
            lead = await self._leads.find_by_id(mapping.lead_id)
            if lead is None:
                continue
            status, editable = await self.external_status_and_editable(lead)
            results.append((lead, status, editable))
        return results, total

    async def get_own_dashboard(self, actor: User) -> ReferralDashboardResponse:
        partner = await self.get_own_partner(actor)
        all_mappings = await self._referral_leads.find_all_for_partner(partner.require_id())

        total_leads = 0
        approved_leads = 0
        rejected_leads = 0
        recent: list[tuple[Lead, str, bool]] = []
        for mapping in sorted(all_mappings, key=lambda m: m.created_at, reverse=True):
            lead = await self._leads.find_by_id(mapping.lead_id)
            if lead is None:
                continue
            total_leads += 1
            status, editable = await self.external_status_and_editable(lead)
            if status == ExternalLeadStatus.APPROVED:
                approved_leads += 1
            elif status == ExternalLeadStatus.REJECTED:
                rejected_leads += 1
            if len(recent) < 5:
                recent.append((lead, status, editable))

        commission = await self._entries.summary_for_partner(partner.require_id())

        return ReferralDashboardResponse(
            total_leads=total_leads, approved_leads=approved_leads, rejected_leads=rejected_leads,
            commission_pending=commission["pending"], commission_approved=commission["approved"],
            commission_paid=commission["paid"], commission_balance=commission["balance"],
            recent_leads=[referral_lead_to_response(lead, status, editable) for lead, status, editable in recent],
        )

    async def list_own_commission_entries(self, actor: User, *, status: str | None, skip: int, limit: int) -> tuple[list[CommissionEntry], int]:
        partner = await self.get_own_partner(actor)
        return await self._entries.search_and_filter(partner_id=partner.require_id(), status=status, skip=skip, limit=limit, sort=[("created_at", -1)])

    # ================================================================== external status mapping

    async def external_status_and_editable(self, lead: Lead) -> tuple[str, bool]:
        """Never exposes an internal Lead/Application/Case status — only these four
        buckets. 'Processing started' (the edit cutoff) is 'an Employee has been
        assigned to this Lead OR an Application already exists for it' — not
        `Lead.status`, which never changes away from 'new' at this stage (Module 6A) and
        so can't signal anything on its own. See docs/decisions/DECISIONS.md."""
        applications = await self._applications.find_many({"lead_id": lead.require_id()}, limit=1)
        application = applications[0] if applications else None
        processing_started = lead.assigned_to is not None or application is not None

        if not processing_started:
            return ExternalLeadStatus.SUBMITTED, True

        if application is not None:
            case = await self._workflows.find_by_application_id(application.require_id())
            if case is not None:
                if case.case_type == CaseType.LOAN and case.current_status == LoanStatus.REJECTED:
                    return ExternalLeadStatus.REJECTED, False
                if case.case_type == CaseType.INSURANCE and case.current_status == InsuranceStatus.REJECTED:
                    return ExternalLeadStatus.REJECTED, False
                if case.case_type == CaseType.LOAN and case.current_status == LoanStatus.DISBURSED:
                    return ExternalLeadStatus.APPROVED, False
                if case.case_type == CaseType.INSURANCE and case.current_status == InsuranceStatus.POLICY_ISSUED:
                    return ExternalLeadStatus.APPROVED, False

        return ExternalLeadStatus.IN_PROGRESS, False

    # ================================================================== Owner: commission rules

    async def create_commission_rule(self, payload: CreateCommissionRuleRequest, actor: User) -> CommissionRule:
        rule = CommissionRule(**payload.model_dump(), created_by=actor.require_id())
        rule_id = await self._rules.insert(rule)
        await write_audit_log(self._db, event_type=AuditEvent.COMMISSION_RULE_CREATED, user_id=actor.require_id(), metadata={"rule_id": rule_id})
        found = await self._rules.find_by_id(rule_id)
        assert found is not None
        return found

    async def list_commission_rules(self) -> list[CommissionRule]:
        return await self._rules.find_many({}, limit=200, sort=[("created_at", 1)])

    async def get_commission_rule(self, rule_id: str) -> CommissionRule:
        rule = await self._rules.find_by_id(rule_id)
        if rule is None:
            raise NotFoundError("Commission rule not found.")
        return rule

    async def update_commission_rule(self, rule_id: str, payload: UpdateCommissionRuleRequest, actor: User) -> CommissionRule:
        updates = payload.model_dump(exclude_unset=True)
        updated = await self._rules.update(rule_id, updates, updated_by=actor.require_id()) if updates else await self._rules.find_by_id(rule_id)
        if updated is None:
            raise NotFoundError("Commission rule not found.")
        await write_audit_log(self._db, event_type=AuditEvent.COMMISSION_RULE_UPDATED, user_id=actor.require_id(), metadata={"rule_id": rule_id})
        return updated

    async def set_commission_rule_active(self, rule_id: str, *, active: bool, actor: User) -> CommissionRule:
        updated = await self._rules.update(rule_id, {"status": "active" if active else "inactive"}, updated_by=actor.require_id())
        if updated is None:
            raise NotFoundError("Commission rule not found.")
        return updated

    # ================================================================== Owner: commission ledger

    async def list_commission_entries(
        self, *, partner_id: str | None, status: str | None, skip: int, limit: int
    ) -> tuple[list[CommissionEntry], int]:
        return await self._entries.search_and_filter(partner_id=partner_id, status=status, skip=skip, limit=limit, sort=[("created_at", -1)])

    async def resolve_partner_names(self, entries: list[CommissionEntry]) -> dict[str, str]:
        partner_ids = {e.partner_id for e in entries}
        if not partner_ids:
            return {}
        partners = await self._partners.find_many({}, limit=1000)
        return {p.require_id(): p.full_name for p in partners if p.require_id() in partner_ids}

    async def approve_commission_entry(self, entry_id: str, actor: User) -> CommissionEntry:
        entry = await self._get_entry(entry_id)
        if entry.status != CommissionEntryStatus.PENDING:
            raise ValidationError("Only a pending commission entry can be approved.")
        updated = await self._entries.update(
            entry_id, {"status": CommissionEntryStatus.APPROVED, "approved_at": utc_now(), "approved_by": actor.require_id()}, updated_by=actor.require_id()
        )
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.COMMISSION_ENTRY_APPROVED, user_id=actor.require_id(), metadata={"entry_id": entry_id})
        return updated

    async def settle_commission_entry(self, entry_id: str, payload: SettleCommissionEntryRequest, actor: User) -> CommissionEntry:
        entry = await self._get_entry(entry_id)
        if entry.status != CommissionEntryStatus.APPROVED:
            raise ValidationError("Only an approved commission entry can be settled/paid.")
        updated = await self._entries.update(
            entry_id,
            {"status": CommissionEntryStatus.PAID, "paid_at": utc_now(), "paid_by": actor.require_id(), "payment_reference": payload.payment_reference},
            updated_by=actor.require_id(),
        )
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.COMMISSION_ENTRY_PAID, user_id=actor.require_id(), metadata={"entry_id": entry_id})
        return updated

    async def _get_entry(self, entry_id: str) -> CommissionEntry:
        entry = await self._entries.find_by_id(entry_id)
        if entry is None:
            raise NotFoundError("Commission entry not found.")
        return entry

    # ================================================================== commission entry creation (worker-driven)

    async def create_commission_entry_if_applicable(self, case: Any) -> CommissionEntry | None:
        """Called only by `app/worker/tasks/referral_partner.py:check_commission_triggers`
        for a case that has just reached a terminal "success" status. Computes the
        commission amount once, from whichever rule applies right now, and stores that
        snapshot — a later edit to `CommissionRule` never changes an already-created
        entry (docs/decisions/DECISIONS.md)."""
        application = await self._applications.find_by_id(case.application_id)
        if application is None or application.lead_id is None:
            return None
        mapping = await self._referral_leads.find_by_lead_id(application.lead_id)
        if mapping is None:
            return None  # not a referral-sourced lead — nothing to do
        if await self._entries.find_existing_for_case(case.require_id()):
            return None  # already created for this case

        trigger, base_amount = self._trigger_and_base_amount(case)
        if trigger is None or base_amount is None:
            return None

        candidates = await self._rules.find_candidates(product_category=case.product_category, partner_id=mapping.partner_id)
        rule = self._pick_rule(candidates, trigger_event=trigger)
        if rule is None:
            return None  # Owner hasn't configured an applicable Commission Rule yet

        commission_amount = base_amount * (rule.rate_or_amount / 100) if rule.calculation_type == CalculationType.PERCENTAGE else rule.rate_or_amount

        entry = CommissionEntry(
            partner_id=mapping.partner_id, lead_id=mapping.lead_id, case_type=case.case_type, case_id=case.require_id(),
            rule_id=rule.require_id(), calculation_type=rule.calculation_type, rate_or_amount=rule.rate_or_amount,
            base_amount=base_amount, commission_amount=commission_amount,
        )
        entry_id = await self._entries.insert(entry)
        await write_audit_log(
            self._db, event_type=AuditEvent.COMMISSION_ENTRY_CREATED, user_id=mapping.partner_id,
            metadata={"entry_id": entry_id, "case_id": case.require_id(), "commission_amount": commission_amount},
        )
        found = await self._entries.find_by_id(entry_id)
        assert found is not None
        return found

    @staticmethod
    def _trigger_and_base_amount(case: Any) -> tuple[str | None, float | None]:
        if case.case_type == CaseType.LOAN and case.current_status == LoanStatus.DISBURSED and case.loan_details is not None:
            return TriggerEvent.LOAN_DISBURSED, case.loan_details.disbursed_amount
        if case.case_type == CaseType.INSURANCE and case.current_status == InsuranceStatus.POLICY_ISSUED and case.insurance_details is not None:
            return TriggerEvent.INSURANCE_POLICY_ISSUED, case.insurance_details.premium_amount
        return None, None

    @staticmethod
    def _pick_rule(candidates: list[CommissionRule], *, trigger_event: str) -> CommissionRule | None:
        matching = [r for r in candidates if r.trigger_event == trigger_event]
        if not matching:
            return None
        # Most specific first: partner-specific + product-specific, then partner-specific
        # + all-products, then default + product-specific, then default + all-products.
        matching.sort(key=lambda r: (r.partner_id is None, r.product_category is None))
        return matching[0]
