"""Partner lifecycle facade over existing identity, referral and financial services.

Owner password provisioning uses accounts.py. Canonical reviewed Applications use
referrals.py. Historical Lead mappings retain their authorized read/edit cutoff.
finance.py is the single commission calculator; Loan earnings run in the confirmed
disbursement transaction, while the legacy worker retains confirmed Insurance events.
"""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.customer.repository import ApplicationRepository
from app.features.leads.models import Lead
from app.features.leads.repository import LeadRepository
from app.features.leads.schemas import UpdateLeadRequest
from app.features.leads.service import LeadService
from app.features.referral_partner_management.constants import (
    ApprovalStatus,
    AuditEvent,
    ExternalLeadStatus,
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
from app.features.system_settings.repository import (
    InsuranceProductRepository,
    LeadSourceRepository,
    LoanProductRepository,
)
from app.features.workflow_engine.constants import CaseType, InsuranceStatus, LoanStatus
from app.features.workflow_engine.repository import ApplicationWorkflowRepository
from app.utils.datetime import utc_now


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
        from app.features.referral_partner_management.accounts import create_account

        return await create_account(self._db, payload, actor)

    async def approve_partner(self, partner_id: str, actor: User) -> ReferralPartner:
        from app.core.exceptions import ConflictError
        from app.features.referral_partner_management.kyc import event, oid
        if actor.role != "owner":
            raise ForbiddenError("Only Owner can activate Partner accounts.")
        partner = await self.get_partner(partner_id)
        if partner.approval_status == ApprovalStatus.ACTIVE and partner.account_active:
            raise ValidationError("Partner is already active.")
        if partner.kyc_status != "approved":
            raise ValidationError("Complete and approve the versioned KYC review first.")
        async with await self._db.client.start_session() as session, session.start_transaction():
            row = await self._db.referral_partners.find_one_and_update(
                {"_id": oid(partner_id), "version": partner.version, "kyc_status": "approved", "is_deleted": False},
                {"$set": {"approval_status": ApprovalStatus.ACTIVE, "account_active": True, "approved_at": utc_now(), "approved_by": actor.require_id()}, "$inc": {"version": 1}}, return_document=True, session=session)
            if not row:
                raise ConflictError("Partner changed; reload before activating.")
            await event(self._db, actor, AuditEvent.PARTNER_APPROVED, partner_id, session=session)
        return ReferralPartner.model_validate(row)

    async def deactivate_partner(self, partner_id: str, actor: User) -> ReferralPartner:
        from app.core.exceptions import ConflictError
        from app.features.referral_partner_management.kyc import event, oid
        if actor.role != "owner":
            raise ForbiddenError("Only Owner can suspend Partner accounts.")
        partner = await self.get_partner(partner_id)
        async with await self._db.client.start_session() as session, session.start_transaction():
            row = await self._db.referral_partners.find_one_and_update(
                {"_id": oid(partner_id), "version": partner.version, "is_deleted": False},
                {"$set": {"approval_status": ApprovalStatus.DEACTIVATED, "account_active": False}, "$inc": {"version": 1}}, return_document=True, session=session)
            if not row:
                raise ConflictError("Partner changed; reload before suspending.")
            await event(self._db, actor, AuditEvent.PARTNER_DEACTIVATED, partner_id, session=session)
        return ReferralPartner.model_validate(row)

    async def list_partners(
        self, *, search: str | None, approval_status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None, kyc_status: str | None = None
    ) -> tuple[list[ReferralPartner], int]:
        return await self._partners.search_and_filter(search=search, approval_status=approval_status, skip=skip, limit=limit, sort=sort, kyc_status=kyc_status)

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
        if not partner.account_active or partner.kyc_status != "approved" or partner.approval_status != ApprovalStatus.ACTIVE:
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
        await self._require_active_partner(actor)
        raise ValidationError("Create a canonical referral Application draft and review it before Submit to AFS. Immediate Lead submission is no longer supported.")

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
            lead_id, UpdateLeadRequest(full_name=payload.full_name, mobile=payload.mobile, email=payload.email, remarks=payload.remarks), actor,
            skip_ownership_check=True,  # already authorized above via the partner-lead mapping + editable-window check
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
        from app.features.referral_partner_management.finance import save_rule
        return await save_rule(self._db, payload, actor)

    async def list_commission_rules(self) -> list[CommissionRule]:
        return await self._rules.find_many({}, limit=200, sort=[("created_at", 1)])

    async def get_commission_rule(self, rule_id: str) -> CommissionRule:
        rule = await self._rules.find_by_id(rule_id)
        if rule is None:
            raise NotFoundError("Commission rule not found.")
        return rule

    async def update_commission_rule(self, rule_id: str, payload: UpdateCommissionRuleRequest, actor: User) -> CommissionRule:
        from app.features.referral_partner_management.finance import save_rule
        return await save_rule(self._db, payload, actor, await self.get_commission_rule(rule_id))

    async def set_commission_rule_active(self, rule_id: str, *, active: bool, actor: User) -> CommissionRule:
        from app.features.referral_partner_management.finance import save_rule
        previous = await self.get_commission_rule(rule_id)
        return await save_rule(self._db, previous.model_copy(update={"status": "active" if active else "inactive"}), actor, previous)

    # ================================================================== Owner: commission ledger

    async def list_commission_entries(
        self, *, partner_id: str | None, status: str | None, skip: int, limit: int
    ) -> tuple[list[CommissionEntry], int]:
        return await self._entries.search_and_filter(partner_id=partner_id, status=status, skip=skip, limit=limit, sort=[("created_at", -1)])

    async def resolve_partner_names(self, entries: list[CommissionEntry]) -> dict[str, str]:
        partner_ids = {e.partner_id for e in entries}
        if not partner_ids:
            return {}
        partners = await self._partners.find_many({"_id": {"$in": [ObjectId(value) for value in partner_ids]}}, limit=len(partner_ids))
        return {p.require_id(): p.full_name for p in partners if p.require_id() in partner_ids}

    async def approve_commission_entry(self, entry_id: str, actor: User) -> CommissionEntry:
        from app.core.exceptions import ConflictError
        from app.features.referral_partner_management.kyc import event, oid
        if actor.role != "owner":
            raise ForbiddenError("Only Owner can approve commissions.")
        from decimal import Decimal

        from pymongo.errors import OperationFailure

        from app.features.referral_partner_management.finance import money
        try:
            async with await self._db.client.start_session() as session, session.start_transaction():
                current = await self._db.commission_entries.find_one({"_id": oid(entry_id), "status": "pending", "is_deleted": False}, session=session)
                if not current:
                    raise ConflictError("Only a current pending commission can be approved.")
                amount = money(current["commission_amount"]) + money(current.get("additional_earned_amount", 0)) + Decimal(str(current.get("adjusted_amount", 0)))
                entry = await self._db.commission_entries.find_one_and_update(
                    {"_id": current["_id"], "version": current["version"], "status": "pending", "is_deleted": False},
                    {"$set": {"status": "approved", "approved_amount": float(max(Decimal(0), amount)), "approved_at": utc_now(), "approved_by": actor.require_id()}, "$inc": {"version": 1}},
                    return_document=True, session=session)
                if not entry:
                    raise ConflictError("Commission changed; reload before approving.")
                await event(self._db, actor, "commission_entry_approved", entry["partner_id"], session=session, detail={"entry_id": entry_id, "approved_version": entry["version"], "approved_earned_amount": entry["commission_amount"] + entry.get("additional_earned_amount", 0), "approved_adjustment": entry.get("adjusted_amount", 0), "approved_amount": entry["approved_amount"]})
        except OperationFailure as exc:
            if exc.code == 112 or exc.has_error_label("TransientTransactionError"):
                raise ConflictError("Commission or payment changed concurrently. Refresh; no automatic retry.") from None
            raise
        return CommissionEntry.model_validate(entry)

    async def settle_commission_entry(self, entry_id: str, payload: SettleCommissionEntryRequest, actor: User) -> CommissionEntry:
        import hashlib

        from app.features.referral_partner_management.finance import PayoutInput, payout
        from app.utils.datetime import to_ist
        entry = await self._get_entry(entry_id)
        amount = entry.commission_amount + entry.additional_earned_amount + entry.adjusted_amount - entry.paid_amount - entry.reserved_amount
        await payout(self._db, entry_id, PayoutInput(
            request_id=hashlib.sha256((entry_id + ":" + payload.payment_reference).encode()).hexdigest(),
            amount=amount, payment_reference=payload.payment_reference,
            payment_method="recorded_payment", payment_date=to_ist(utc_now()).date().isoformat(),
            confirmed=True), actor)
        return await self._get_entry(entry_id)

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
        existing = await self._entries.find_existing_for_case(case.require_id())
        if existing or case.case_type != CaseType.INSURANCE:
            # Loan earnings belong to the disbursement transaction; no historical Loan backfill.
            return existing
        from app.features.referral_partner_management.finance import calculate
        from app.features.referral_partner_management.kyc import oid
        history = await self._db.application_status_history.find_one({"application_workflow_id": case.require_id(), "to_status": InsuranceStatus.POLICY_ISSUED}, sort=[("created_at", -1)])
        if not history:
            return None
        class SystemActor:
            role = "system"
            def require_id(self) -> None:
                return None
        async with await self._db.client.start_session() as session, session.start_transaction():
            current = await self._db.application_workflows.find_one({"_id": oid(case.require_id()), "current_status": InsuranceStatus.POLICY_ISSUED, "is_deleted": False}, session=session)
            if not current:
                return None
            await self._db.application_workflows.update_one({"_id": current["_id"], "version": current["version"]}, {"$inc": {"commission_guard": 1}}, session=session)
            await calculate(self._db, current, SystemActor(), session, str(history["_id"]))
        return await self._entries.find_existing_for_case(case.require_id())
