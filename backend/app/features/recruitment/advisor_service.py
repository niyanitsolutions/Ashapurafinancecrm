"""Advisor Management (Phase 2) — business logic.

Same authorization posture as `RecruitmentService`: the router gates every route with
`require_permission("insurance_management", "recruitment", action)` (Phase 2 reuses the
Phase 1 resource — no new permission). This service owns the Advisor list (filtered by
Profession / Type / Status, three independent fields) and the `AdvisorBusiness` records
whose `$sum` is the advisor's policy count / total premium.
"""

from collections.abc import Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.recruitment.constants import (
    AdvisorChannel,
    AdvisorProductCategory,
    AdvisorStatus,
    Profession,
    RecruitmentAuditEvent,
)
from app.features.recruitment.models import Advisor, AdvisorBusiness, RecruitmentLead
from app.features.recruitment.repository import (
    AdvisorBusinessRepository,
    AdvisorRepository,
    RecruitmentLeadRepository,
)
from app.features.recruitment.schemas import AddAdvisorBusinessRequest, UpdateAdvisorRequest
from app.features.recruitment.service import RecruitmentService
from app.security.password import hash_password
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_to_utc_midnight


class AdvisorService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._advisors = AdvisorRepository(db)
        self._business = AdvisorBusinessRepository(db)
        self._leads = RecruitmentLeadRepository(db)
        self._employees = EmployeeRepository(db)
        # Reused only for name resolution + presigned download URLs on the detail view.
        self._recruitment = RecruitmentService(db)

    # ---------------------------------------------------------------- employee matching

    async def _employee_mobiles(self) -> set[str]:
        # Only used to flag an advisor row as "(employee)" for display — never a filter.
        return {e.mobile for e in await self._employees.find_many({}, limit=5000)}

    # ---------------------------------------------------------------- list

    async def list_advisors(
        self, _actor: User, *, channel: str | None, profession: str | None, status: str | None,
        search: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[tuple[Advisor, bool, int, float]], int]:
        # Profession, Type (channel) and Status are three independent, indexed equality
        # filters. `None` for any of them = "All" (no restriction); they combine with AND.
        if channel is not None and channel not in AdvisorChannel.ALL:
            raise ValidationError(f"Unknown Type: {channel}")
        if profession is not None and profession not in Profession.ALL:
            raise ValidationError(f"Unknown profession: {profession}")
        if status is not None and status not in AdvisorStatus.ALL:
            raise ValidationError(f"Unknown status: {status}")

        page, total = await self._advisors.search_and_filter(
            search=search, channel=channel, status=status, profession=profession,
            skip=skip, limit=limit, sort=sort,
        )
        employee_mobiles = await self._employee_mobiles()
        aggregates = await self._business.aggregate_by_advisor([a.require_id() for a in page])
        rows: list[tuple[Advisor, bool, int, float]] = []
        for advisor in page:
            count, premium = aggregates.get(advisor.require_id(), (0, 0.0))
            rows.append((advisor, advisor.mobile in employee_mobiles, count, premium))
        return rows, total

    # ---------------------------------------------------------------- detail

    async def get_advisor(self, advisor_id: str) -> Advisor:
        advisor = await self._advisors.find_by_id(advisor_id)
        if advisor is None:
            raise NotFoundError("Advisor not found.")
        return advisor

    async def get_advisor_detail(self, advisor_id: str) -> tuple[Advisor, bool, int, float, list[AdvisorBusiness]]:
        advisor = await self.get_advisor(advisor_id)
        employee_mobiles = await self._employee_mobiles()
        aggregates = await self._business.aggregate_by_advisor([advisor_id])
        count, premium = aggregates.get(advisor_id, (0, 0.0))
        businesses = await self._business.find_for_advisor(advisor_id)
        return advisor, advisor.mobile in employee_mobiles, count, premium, businesses

    async def get_linked_recruitment(
        self, advisor: Advisor
    ) -> tuple[RecruitmentLead, str, str, Callable[[str | None], str | None]] | None:
        lead = await self._leads.find_by_id(advisor.recruitment_lead_id)
        if lead is None:
            return None
        source_map, employee_map = await self._recruitment.resolve_names([lead])
        return (
            lead,
            source_map.get(lead.source_id, ""),
            employee_map.get(lead.assigned_to or "") or "",
            self._recruitment.download_url,
        )

    # ---------------------------------------------------------------- mutations

    async def update_advisor(self, advisor_id: str, payload: UpdateAdvisorRequest, actor: User) -> Advisor:
        advisor = await self.get_advisor(advisor_id)
        updates: dict[str, Any] = {}

        if payload.agency_code is not None:
            updates["agency_code"] = payload.agency_code.strip() or None
        if payload.agent_code is not None:
            updates["agent_code"] = payload.agent_code.strip() or None
        # 2026 redesign: QR / Non-QR is an explicit choice, NOT derived from `agency_code`.
        if payload.channel is not None:
            updates["channel"] = payload.channel
        if payload.status is not None:
            updates["status"] = payload.status
        if payload.password:
            # Blank input = "keep the current password" (never hash an empty string).
            # Write-only: store the hash, never echo the plaintext (or the hash) anywhere.
            # No length/complexity policy on this field (see UpdateAdvisorRequest); bcrypt's
            # 72-byte cap is still enforced by hash_password.
            updates["password_hash"] = hash_password(payload.password)

        if not updates:
            return advisor

        updated = await self._advisors.update(advisor_id, updates, updated_by=actor.require_id())
        assert updated is not None
        audit_meta: dict[str, Any] = {"advisor_id": advisor_id}
        for key in ("agency_code", "agent_code", "channel", "status"):
            if key in updates:
                audit_meta[key] = updates[key]
        if "password_hash" in updates:
            audit_meta["password_changed"] = True  # never the value
        await write_audit_log(
            self._db, event_type=RecruitmentAuditEvent.ADVISOR_UPDATED, user_id=actor.require_id(),
            metadata=audit_meta,
        )
        return updated

    async def add_business(self, advisor_id: str, payload: AddAdvisorBusinessRequest, actor: User) -> AdvisorBusiness:
        await self.get_advisor(advisor_id)
        business = AdvisorBusiness(
            advisor_id=advisor_id,
            customer_name=(payload.customer_name or "").strip() or None,
            customer_mobile=payload.customer_mobile or None,
            policy_number=(payload.policy_number or "").strip() or None,
            product_category=payload.product_category,
            custom_category=payload.custom_category if payload.product_category == AdvisorProductCategory.CUSTOM else None,
            product_name=payload.product_name.strip(),
            premium=payload.premium,
            ppt=payload.ppt,
            pt=payload.pt,
            policy_issue_date=ist_date_to_utc_midnight(payload.policy_issue_date),
            comment=(payload.comment or "").strip() or None,
            created_by=actor.require_id(),
        )
        business_id = await self._business.insert(business)
        await write_audit_log(
            self._db, event_type=RecruitmentAuditEvent.ADVISOR_BUSINESS_ADDED, user_id=actor.require_id(),
            metadata={"advisor_id": advisor_id, "advisor_business_id": business_id, "premium": payload.premium},
        )
        created = await self._business.find_by_id(business_id)
        assert created is not None
        return created

    async def list_business(self, advisor_id: str) -> list[AdvisorBusiness]:
        await self.get_advisor(advisor_id)
        return await self._business.find_for_advisor(advisor_id)
