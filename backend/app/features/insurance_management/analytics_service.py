from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import PermissionRepository
from app.features.auth.models import User
from app.features.insurance_management.analytics_repository import InsuranceAnalyticsRepository
from app.features.insurance_management.analytics_schemas import (
    AdvisorAnalyticsRow,
    AdvisorBusinessAnalyticsItem,
    AdvisorProductMetric,
    AdvisorWorkAnalytics,
    AnalyticsCapabilities,
    AnalyticsFilterOption,
    InsuranceAnalyticsOverview,
    InsuranceAnalyticsSummary,
    PipelineStageMetric,
    PolicyAnalyticsItem,
    ProductAnalyticsRow,
    ProductWorkAnalytics,
)
from app.features.insurance_management.service import InsuranceCaseService
from app.features.recruitment.repository import AdvisorRepository
from app.features.system_settings.repository import InsuranceProductRepository
from app.features.workflow_engine.constants import CaseType, InsuranceStatus
from app.utils.datetime import ist_date_range_to_utc_bounds
from app.utils.helpers import is_valid_object_id


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class InsuranceAnalyticsService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._repo = InsuranceAnalyticsRepository(db)
        self._permissions = PermissionRepository(db)
        self._engine = PermissionEngine(db)
        self._cases = InsuranceCaseService(db)
        self._advisors = AdvisorRepository(db)
        self._products = InsuranceProductRepository(db)

    async def _can_view_advisors(self, actor: User) -> bool:
        return await self._engine.has_permission(
            actor, module="insurance_management", resource="advisors", action="view"
        )

    async def _allowed_statuses(self, actor: User) -> list[str]:
        parent = await self._engine.has_permission(
            actor, module="insurance_management", resource="applications", action="view"
        )
        allowed: list[str] = []
        for status in InsuranceStatus.ALL:
            resource = f"applications.{status}"
            child = await self._permissions.find_by_module_resource(
                "insurance_management", resource
            )
            if (child is None and parent) or (
                child is not None
                and await self._engine.has_permission(
                    actor, module="insurance_management", resource=resource, action="view"
                )
            ):
                allowed.append(status)
        return allowed

    async def capabilities(self, actor: User) -> AnalyticsCapabilities:
        return AnalyticsCapabilities(
            advisor_business=await self._can_view_advisors(actor),
            policy_pipeline=bool(await self._allowed_statuses(actor)),
        )

    @staticmethod
    def _bounds(date_from: date | None, date_to: date | None) -> tuple[Any, Any]:
        if date_from and date_to and date_from > date_to:
            raise ValidationError("date_from must be on or before date_to.")
        return ist_date_range_to_utc_bounds(date_from, date_to)

    async def _validate_advisor(self, advisor_id: str | None) -> None:
        if advisor_id and (
            not is_valid_object_id(advisor_id)
            or await self._advisors.find_by_id(advisor_id) is None
        ):
            raise NotFoundError("Advisor not found.")

    async def _validate_product(self, product_id: str | None) -> None:
        if product_id and (
            not is_valid_object_id(product_id)
            or await self._products.find_by_id(product_id) is None
        ):
            raise NotFoundError("Insurance product not found.")

    async def _policy_query(
        self,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        advisor_id: str | None,
        product_id: str | None,
        stage: str | None,
    ) -> tuple[dict[str, Any], list[str]]:
        allowed = await self._allowed_statuses(actor)
        if not allowed:
            raise ForbiddenError("Missing Insurance Policy Leads view permission.")
        if stage is not None and stage not in InsuranceStatus.ALL:
            raise ValidationError("Unknown insurance stage.")
        if stage is not None and stage not in allowed:
            raise ForbiddenError("Missing permission for this Insurance stage.")
        await self._validate_advisor(advisor_id)
        await self._validate_product(product_id)
        lower, upper = self._bounds(date_from, date_to)
        query: dict[str, Any] = {
            "is_deleted": False,
            "case_type": CaseType.INSURANCE,
            "current_status": stage or {"$in": allowed},
        }
        if advisor_id:
            query["assigned_to"] = advisor_id
        if product_id:
            query["product_id"] = product_id
        if lower is not None or upper is not None:
            date_query = {
                **({"$gte": lower} if lower else {}),
                **({"$lt": upper} if upper else {}),
            }
            query["$or"] = [
                {
                    "current_status": InsuranceStatus.POLICY_ISSUED,
                    "insurance_details.policy_issue_date": date_query,
                },
                {
                    "current_status": {"$ne": InsuranceStatus.POLICY_ISSUED},
                    "created_at": date_query,
                },
            ]
        if actor.role == EMPLOYEE:
            query.update(await self._cases._employee_scope_filter(actor))
        return query, allowed

    async def overview(
        self,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        advisor_id: str | None,
        product_id: str | None,
        stage: str | None,
    ) -> InsuranceAnalyticsOverview:
        caps = await self.capabilities(actor)
        if not caps.advisor_business and not caps.policy_pipeline:
            raise ForbiddenError("Missing Insurance Analytics access.")
        summary = InsuranceAnalyticsSummary()
        pipeline: list[PipelineStageMetric] = []
        advisor_options: list[AnalyticsFilterOption] = []
        product_options: list[AnalyticsFilterOption] = []
        stages: list[str] = []
        lower, upper = self._bounds(date_from, date_to)
        await self._validate_advisor(advisor_id)
        if caps.advisor_business:
            advisor_options = [
                AnalyticsFilterOption(id=item.require_id(), label=item.full_name)
                for item in await self._advisors.find_many({}, limit=1000, sort=[("full_name", 1)])
            ]
            summary.total_advisors = await self._repo.count_advisors(advisor_id)
            summary.total_business, premium = await self._repo.advisor_summary(
                advisor_id=advisor_id, lower=lower, upper=upper
            )
            summary.business_premium = _money(premium)
        if caps.policy_pipeline:
            product_options = [
                AnalyticsFilterOption(id=item.require_id(), label=item.name)
                for item in await self._products.find_many({}, limit=500, sort=[("name", 1)])
            ]
            query, allowed = await self._policy_query(
                actor,
                date_from=date_from,
                date_to=date_to,
                advisor_id=advisor_id,
                product_id=product_id,
                stage=stage,
            )
            if not caps.advisor_business:
                advisor_options = [
                    AnalyticsFilterOption(id=str(item["_id"]), label=item["full_name"])
                    for item in await self._repo.policy_advisors(query)
                ]
            stages = allowed
            total, issued, premium, counts = await self._repo.policy_overview(query)
            summary.total_policy_leads, summary.total_policy_issued, summary.policy_premium = (
                total,
                issued,
                _money(premium),
            )
            pipeline = [
                PipelineStageMetric(stage=value, count=counts.get(value, 0))
                for value in allowed
                if stage is None or value == stage
            ]
        return InsuranceAnalyticsOverview(
            capabilities=caps,
            summary=summary,
            pipeline=pipeline,
            stages=stages,
            advisors=advisor_options,
            products=product_options,
        )

    async def advisors(
        self,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        advisor_id: str | None,
        skip: int,
        limit: int,
    ) -> tuple[list[AdvisorAnalyticsRow], int]:
        if not await self._can_view_advisors(actor):
            raise ForbiddenError("Missing Advisors view permission.")
        await self._validate_advisor(advisor_id)
        lower, upper = self._bounds(date_from, date_to)
        rows, total = await self._repo.advisor_rows(
            advisor_id=advisor_id, lower=lower, upper=upper, skip=skip, limit=limit
        )
        result: list[AdvisorAnalyticsRow] = []
        for row in rows:
            advisor, metric = row["advisor"], row["metrics"] or {}
            result.append(
                AdvisorAnalyticsRow(
                    advisor_id=str(advisor["_id"]),
                    advisor_code=advisor["advisor_code"],
                    advisor_name=advisor["full_name"],
                    businesses=int(metric.get("businesses", 0)),
                    total_premium=_money(float(metric.get("premium", 0))),
                    products=len(metric.get("products", [])),
                )
            )
        return result, total

    async def advisor_work(
        self,
        actor: User,
        advisor_id: str,
        *,
        date_from: date | None,
        date_to: date | None,
        skip: int,
        limit: int,
    ) -> tuple[AdvisorWorkAnalytics, int]:
        if not await self._can_view_advisors(actor):
            raise ForbiddenError("Missing Advisors view permission.")
        await self._validate_advisor(advisor_id)
        lower, upper = self._bounds(date_from, date_to)
        advisor, metric, businesses, total, products = await self._repo.advisor_work(
            advisor_id=advisor_id, lower=lower, upper=upper, skip=skip, limit=limit
        )
        assert advisor is not None
        row = AdvisorAnalyticsRow(
            advisor_id=advisor_id,
            advisor_code=advisor["advisor_code"],
            advisor_name=advisor["full_name"],
            businesses=metric["businesses"],
            total_premium=_money(metric["premium"]),
            products=metric["products"],
        )
        items = [
            AdvisorBusinessAnalyticsItem(
                id=item.require_id(),
                customer_name=item.customer_name,
                customer_mobile=item.customer_mobile,
                policy_number=item.policy_number,
                product_name=item.product_name,
                product_category=item.custom_category or item.product_category,
                premium=_money(item.premium),
                ppt=item.ppt,
                pt=item.pt,
                policy_issue_date=item.policy_issue_date,
                comment=item.comment,
                created_at=item.created_at,
            )
            for item in businesses
        ]
        breakdown = [
            AdvisorProductMetric(product_name=str(item["_id"]), businesses=int(item["businesses"]))
            for item in products
        ]
        return AdvisorWorkAnalytics(advisor=row, products=breakdown, businesses=items), total

    async def products(
        self,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        advisor_id: str | None,
        product_id: str | None,
        stage: str | None,
        skip: int,
        limit: int,
    ) -> tuple[list[ProductAnalyticsRow], int]:
        query, _ = await self._policy_query(
            actor,
            date_from=date_from,
            date_to=date_to,
            advisor_id=advisor_id,
            product_id=product_id,
            stage=stage,
        )
        rows, total = await self._repo.product_rows(query, skip=skip, limit=limit)
        names = {
            item.require_id(): item.name for item in await self._products.find_many({}, limit=500)
        }
        return [
            ProductAnalyticsRow(
                product_id=row["_id"],
                product_name=names.get(row["_id"], "Unknown product"),
                leads=int(row["leads"]),
                issued=int(row["issued"]),
                premium=_money(float(row["premium"])),
            )
            for row in rows
        ], total

    async def product_work(
        self,
        actor: User,
        product_id: str,
        *,
        date_from: date | None,
        date_to: date | None,
        advisor_id: str | None,
        stage: str | None,
        skip: int,
        limit: int,
    ) -> tuple[ProductWorkAnalytics, int]:
        await self._validate_product(product_id)
        query, _ = await self._policy_query(
            actor,
            date_from=date_from,
            date_to=date_to,
            advisor_id=advisor_id,
            product_id=product_id,
            stage=stage,
        )
        metric, cases, total = await self._repo.product_work(query, skip=skip, limit=limit)
        customer_map, product_map, advisor_map, _ = await self._cases.resolve_names(cases)
        product = ProductAnalyticsRow(
            product_id=product_id,
            product_name=product_map.get(product_id, "Unknown product"),
            leads=metric["leads"],
            issued=metric["issued"],
            premium=_money(metric["premium"]),
        )
        items = [
            PolicyAnalyticsItem(
                id=item.require_id(),
                case_code=item.case_code,
                customer_id=item.customer_id,
                customer_name=customer_map.get(item.customer_id),
                advisor_id=item.assigned_to,
                advisor_name=advisor_map.get(item.assigned_to or ""),
                product_id=item.product_id,
                product_name=product_map.get(item.product_id, "Unknown product"),
                stage=item.current_status,
                premium=item.insurance_details.premium_amount if item.insurance_details else None,
                created_at=item.created_at,
            )
            for item in cases
        ]
        return ProductWorkAnalytics(product=product, leads=items), total
