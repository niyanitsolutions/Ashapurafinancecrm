from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.recruitment.models import AdvisorBusiness
from app.features.workflow_engine.models import ApplicationWorkflow
from app.utils.helpers import is_valid_object_id, to_object_id


def _date_filter(lower: datetime | None, upper: datetime | None) -> dict[str, datetime]:
    value: dict[str, datetime] = {}
    if lower is not None:
        value["$gte"] = lower
    if upper is not None:
        value["$lt"] = upper
    return value


class InsuranceAnalyticsRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._advisors = db["advisors"]
        self._business = db["advisor_business"]
        self._workflows = db["application_workflows"]

    async def count_advisors(self, advisor_id: str | None) -> int:
        query: dict[str, Any] = {"is_deleted": False}
        if advisor_id:
            query["_id"] = to_object_id(advisor_id)
        return await self._advisors.count_documents(query)

    async def advisor_summary(
        self, *, advisor_id: str | None, lower: datetime | None, upper: datetime | None
    ) -> tuple[int, float]:
        query: dict[str, Any] = {"is_deleted": False}
        if advisor_id:
            query["advisor_id"] = advisor_id
        if lower is not None or upper is not None:
            query["created_at"] = _date_filter(lower, upper)
        pipeline = [
            {"$match": query},
            {"$group": {"_id": None, "count": {"$sum": 1}, "premium": {"$sum": "$premium"}}},
        ]
        rows = [row async for row in self._business.aggregate(pipeline)]
        return (int(rows[0]["count"]), float(rows[0]["premium"])) if rows else (0, 0.0)

    async def advisor_rows(
        self,
        *,
        advisor_id: str | None,
        lower: datetime | None,
        upper: datetime | None,
        skip: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if advisor_id:
            query["_id"] = to_object_id(advisor_id)
        total = await self._advisors.count_documents(query)
        advisors = [
            row
            async for row in self._advisors.find(query).sort("full_name", 1).skip(skip).limit(limit)
        ]
        ids = [str(row["_id"]) for row in advisors]
        business_query: dict[str, Any] = {"is_deleted": False, "advisor_id": {"$in": ids}}
        if lower is not None or upper is not None:
            business_query["created_at"] = _date_filter(lower, upper)
        pipeline = [
            {"$match": business_query},
            {
                "$group": {
                    "_id": "$advisor_id",
                    "businesses": {"$sum": 1},
                    "premium": {"$sum": "$premium"},
                    "products": {"$addToSet": "$product_name"},
                }
            },
        ]
        metrics = {row["_id"]: row async for row in self._business.aggregate(pipeline)}
        return [
            {"advisor": row, "metrics": metrics.get(str(row["_id"]))} for row in advisors
        ], total

    async def advisor_work(
        self,
        *,
        advisor_id: str,
        lower: datetime | None,
        upper: datetime | None,
        skip: int,
        limit: int,
    ) -> tuple[
        dict[str, Any] | None, dict[str, Any], list[AdvisorBusiness], int, list[dict[str, Any]]
    ]:
        advisor = await self._advisors.find_one(
            {"_id": to_object_id(advisor_id), "is_deleted": False}
        )
        query: dict[str, Any] = {"advisor_id": advisor_id, "is_deleted": False}
        if lower is not None or upper is not None:
            query["created_at"] = _date_filter(lower, upper)
        total = await self._business.count_documents(query)
        docs = [
            AdvisorBusiness.model_validate(row)
            async for row in self._business.find(query)
            .sort([("created_at", -1)])
            .skip(skip)
            .limit(limit)
        ]
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": "$product_name",
                    "businesses": {"$sum": 1},
                    "premium": {"$sum": "$premium"},
                }
            },
            {"$sort": {"businesses": -1, "_id": 1}},
        ]
        products = [row async for row in self._business.aggregate(pipeline)]
        summary = {
            "businesses": sum(int(row["businesses"]) for row in products),
            "premium": sum(float(row["premium"]) for row in products),
            "products": len(products),
        }
        return advisor, summary, docs, total, products

    async def policy_overview(
        self, query: dict[str, Any]
    ) -> tuple[int, int, float, dict[str, int]]:
        summary_pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "issued": {
                        "$sum": {"$cond": [{"$eq": ["$current_status", "policy_issued"]}, 1, 0]}
                    },
                    "premium": {"$sum": {"$ifNull": ["$insurance_details.premium_amount", 0]}},
                }
            },
        ]
        rows = [row async for row in self._workflows.aggregate(summary_pipeline)]
        pipeline = [{"$match": query}, {"$group": {"_id": "$current_status", "count": {"$sum": 1}}}]
        counts = {
            row["_id"]: int(row["count"]) async for row in self._workflows.aggregate(pipeline)
        }
        if not rows:
            return 0, 0, 0.0, counts
        return int(rows[0]["total"]), int(rows[0]["issued"]), float(rows[0]["premium"]), counts

    async def policy_advisors(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        assigned = await self._workflows.distinct("assigned_to", query)
        advisor_ids = [to_object_id(value) for value in assigned if is_valid_object_id(value)]
        if not advisor_ids:
            return []
        return [
            row
            async for row in self._advisors.find(
                {"_id": {"$in": advisor_ids}, "is_deleted": False}
            ).sort("full_name", 1)
        ]

    async def product_rows(
        self, query: dict[str, Any], *, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        grouped = [
            {"$match": query},
            {
                "$group": {
                    "_id": "$product_id",
                    "leads": {"$sum": 1},
                    "issued": {
                        "$sum": {"$cond": [{"$eq": ["$current_status", "policy_issued"]}, 1, 0]}
                    },
                    "premium": {"$sum": {"$ifNull": ["$insurance_details.premium_amount", 0]}},
                }
            },
            {"$sort": {"leads": -1, "_id": 1}},
        ]
        all_rows = [row async for row in self._workflows.aggregate(grouped)]
        return all_rows[skip : skip + limit], len(all_rows)

    async def product_work(
        self, query: dict[str, Any], *, skip: int, limit: int
    ) -> tuple[dict[str, Any], list[ApplicationWorkflow], int]:
        total, issued, premium, _ = await self.policy_overview(query)
        docs = [
            ApplicationWorkflow.model_validate(row)
            async for row in self._workflows.find(query)
            .sort([("created_at", -1)])
            .skip(skip)
            .limit(limit)
        ]
        return {"leads": total, "issued": issued, "premium": premium}, docs, total
