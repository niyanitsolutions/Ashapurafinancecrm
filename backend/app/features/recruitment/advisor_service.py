"""Advisor Management (Phase 2) — business logic.

Same authorization posture as `RecruitmentService`: the router gates every route with
`require_permission("insurance_management", "recruitment", action)` (Phase 2 reuses the
Phase 1 resource — no new permission). This service owns the Advisor list/filters, the
QR-vs-Non-QR classification (derived from `agency_code`), and the `AdvisorBusiness`
records whose `$sum` is the advisor's policy count / total premium.
"""

from collections.abc import Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.employee.repository import EmployeeRepository
from app.features.recruitment.constants import (
    AdvisorChannel,
    AdvisorFilter,
    AdvisorProductCategory,
    AdvisorStatus,
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
        return {e.mobile for e in await self._employees.find_many({}, limit=5000)}

    @staticmethod
    def _matches_filter(advisor: Advisor, *, is_employee: bool, filter_key: str | None) -> bool:
        if filter_key == AdvisorFilter.INDIVIDUAL:
            return not is_employee
        if filter_key == AdvisorFilter.TOTAL_EMPLOYEES:
            return is_employee
        if filter_key == AdvisorFilter.ACTIVE:
            return advisor.status == AdvisorStatus.ACTIVE
        if filter_key == AdvisorFilter.INACTIVE:
            return advisor.status == AdvisorStatus.INACTIVE
        return True

    # ---------------------------------------------------------------- list / counts

    async def list_advisors(
        self, _actor: User, *, channel: str | None, filter_key: str | None, search: str | None,
        skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[tuple[Advisor, bool, int, float]], int]:
        if filter_key is not None and filter_key not in AdvisorFilter.ALL:
            raise ValidationError(f"Unknown filter: {filter_key}")
        if channel is not None and channel not in AdvisorChannel.ALL:
            raise ValidationError(f"Unknown channel: {channel}")

        # The Individual / Total-Employees split can't be expressed as a Mongo query
        # (it depends on a cross-collection mobile match), so those two filters page in
        # Python; Active/Inactive/none page in the DB.
        status_filter = filter_key if filter_key in (AdvisorFilter.ACTIVE, AdvisorFilter.INACTIVE) else None
        needs_python_paging = filter_key in (AdvisorFilter.INDIVIDUAL, AdvisorFilter.TOTAL_EMPLOYEES)
        employee_mobiles = await self._employee_mobiles()

        if needs_python_paging:
            all_matching, _ = await self._advisors.search_and_filter(
                search=search, channel=channel, status=None, skip=0, limit=100_000, sort=sort
            )
            filtered = [a for a in all_matching if self._matches_filter(a, is_employee=a.mobile in employee_mobiles, filter_key=filter_key)]
            total = len(filtered)
            page = filtered[skip : skip + limit]
        else:
            page, total = await self._advisors.search_and_filter(
                search=search, channel=channel, status=status_filter, skip=skip, limit=limit, sort=sort
            )

        aggregates = await self._business.aggregate_by_advisor([a.require_id() for a in page])
        rows: list[tuple[Advisor, bool, int, float]] = []
        for advisor in page:
            count, premium = aggregates.get(advisor.require_id(), (0, 0.0))
            rows.append((advisor, advisor.mobile in employee_mobiles, count, premium))
        return rows, total

    async def get_counts(self, _actor: User, *, channel: str | None) -> dict[str, int]:
        qr = await self._advisors.count_advisors(channel=AdvisorChannel.QR)
        non_qr = await self._advisors.count_advisors(channel=AdvisorChannel.NON_QR)

        scoped, _ = await self._advisors.search_and_filter(
            search=None, channel=channel, status=None, skip=0, limit=100_000, sort=None
        )
        employee_mobiles = await self._employee_mobiles()
        individual = sum(1 for a in scoped if a.mobile not in employee_mobiles)
        return {
            "qr": qr,
            "non_qr": non_qr,
            "total": len(scoped),
            "individual": individual,
            "total_employees": len(scoped) - individual,
            "active": sum(1 for a in scoped if a.status == AdvisorStatus.ACTIVE),
            "inactive": sum(1 for a in scoped if a.status == AdvisorStatus.INACTIVE),
        }

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
            code = payload.agency_code.strip() or None
            updates["agency_code"] = code
            # QR is derived from the agency code — keep the stored `channel` in lockstep.
            updates["channel"] = AdvisorChannel.QR if code else AdvisorChannel.NON_QR
        if payload.status is not None:
            updates["status"] = payload.status

        if not updates:
            return advisor

        updated = await self._advisors.update(advisor_id, updates, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(
            self._db, event_type=RecruitmentAuditEvent.ADVISOR_UPDATED, user_id=actor.require_id(),
            metadata={"advisor_id": advisor_id, **updates},
        )
        return updated

    async def add_business(self, advisor_id: str, payload: AddAdvisorBusinessRequest, actor: User) -> AdvisorBusiness:
        await self.get_advisor(advisor_id)
        business = AdvisorBusiness(
            advisor_id=advisor_id,
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
