import re
from typing import Any

from app.features.recruitment.models import (
    Advisor,
    AdvisorBusiness,
    RecruitmentActivity,
    RecruitmentLead,
    RecruitmentNote,
)
from app.shared.base_repository import BaseRepository
from app.utils.helpers import to_object_id

_SEARCH_FIELDS = ("recruitment_code", "full_name", "mobile", "email")


class RecruitmentLeadRepository(BaseRepository[RecruitmentLead]):
    collection_name = "recruitment_leads"
    model = RecruitmentLead

    async def find_by_mobile(self, mobile: str, *, exclude_id: str | None = None) -> list[RecruitmentLead]:
        query: dict[str, Any] = {"mobile": mobile, "is_deleted": False}
        if exclude_id:
            query["_id"] = {"$ne": to_object_id(exclude_id)}
        return [self.model.model_validate(doc) async for doc in self.collection.find(query)]

    def build_scoped_query(
        self,
        *,
        search: str | None = None,
        stage: str | None = None,
        stage_in: tuple[str, ...] | None = None,
        assigned_to: str | None = None,
        scope_user_id: str | None = None,
        scope_employee_id: str | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"is_deleted": False}
        if stage:
            query["stage"] = stage
        elif stage_in:
            query["stage"] = {"$in": list(stage_in)}
        if assigned_to:
            query["assigned_to"] = assigned_to
        # Non-Owner visibility: leads the actor created OR that are assigned to them.
        if scope_user_id is not None or scope_employee_id is not None:
            query["$or"] = [
                {"created_by": scope_user_id},
                {"assigned_to": scope_employee_id},
            ]
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$and"] = [{"$or": [{field: pattern} for field in _SEARCH_FIELDS]}]
        return query

    async def search_and_filter(
        self,
        *,
        search: str | None,
        stage: str | None = None,
        stage_in: tuple[str, ...] | None = None,
        assigned_to: str | None = None,
        scope_user_id: str | None = None,
        scope_employee_id: str | None = None,
        skip: int,
        limit: int,
        sort: list[tuple[str, int]] | None,
    ) -> tuple[list[RecruitmentLead], int]:
        query = self.build_scoped_query(
            search=search, stage=stage, stage_in=stage_in, assigned_to=assigned_to,
            scope_user_id=scope_user_id, scope_employee_id=scope_employee_id,
        )
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort(sort or [("created_at", -1)])
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def count_stage(
        self,
        *,
        stage: str | None = None,
        stage_in: tuple[str, ...] | None = None,
        scope_user_id: str | None = None,
        scope_employee_id: str | None = None,
    ) -> int:
        query = self.build_scoped_query(
            stage=stage, stage_in=stage_in, scope_user_id=scope_user_id, scope_employee_id=scope_employee_id,
        )
        return await self.collection.count_documents(query)


class RecruitmentActivityRepository(BaseRepository[RecruitmentActivity]):
    collection_name = "recruitment_activities"
    model = RecruitmentActivity

    async def find_for_lead(self, recruitment_lead_id: str) -> list[RecruitmentActivity]:
        return await self.find_many({"recruitment_lead_id": recruitment_lead_id}, limit=500, sort=[("created_at", -1)])


class RecruitmentNoteRepository(BaseRepository[RecruitmentNote]):
    collection_name = "recruitment_notes"
    model = RecruitmentNote

    async def find_for_lead(self, recruitment_lead_id: str) -> list[RecruitmentNote]:
        return await self.find_many({"recruitment_lead_id": recruitment_lead_id}, limit=500, sort=[("created_at", -1)])


_ADVISOR_SEARCH_FIELDS = ("advisor_code", "full_name", "mobile", "email")


class AdvisorRepository(BaseRepository[Advisor]):
    collection_name = "advisors"
    model = Advisor

    async def find_by_recruitment_lead_id(self, recruitment_lead_id: str) -> Advisor | None:
        doc = await self.collection.find_one({"recruitment_lead_id": recruitment_lead_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    @staticmethod
    def build_query(
        *, search: str | None = None, channel: str | None = None, status: str | None = None,
        profession: str | None = None,
    ) -> dict[str, Any]:
        # `channel` (Type), `status` and `profession` are independent, indexed equality
        # filters — any combination narrows the result; omitting one means "no restriction".
        query: dict[str, Any] = {"is_deleted": False}
        if channel:
            query["channel"] = channel
        if status:
            query["status"] = status
        if profession:
            query["profession"] = profession
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{field: pattern} for field in _ADVISOR_SEARCH_FIELDS]
        return query

    async def search_and_filter(
        self, *, search: str | None, channel: str | None, status: str | None, profession: str | None,
        skip: int, limit: int, sort: list[tuple[str, int]] | None,
    ) -> tuple[list[Advisor], int]:
        query = self.build_query(search=search, channel=channel, status=status, profession=profession)
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort(sort or [("created_at", -1)])
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class AdvisorBusinessRepository(BaseRepository[AdvisorBusiness]):
    collection_name = "advisor_business"
    model = AdvisorBusiness

    async def find_for_advisor(self, advisor_id: str) -> list[AdvisorBusiness]:
        return await self.find_many({"advisor_id": advisor_id}, limit=1000, sort=[("policy_issue_date", -1), ("created_at", -1)])

    async def aggregate_by_advisor(self, advisor_ids: list[str]) -> dict[str, tuple[int, float]]:
        """`{advisor_id: (policy_count, total_premium)}` — one `$group` pass (pattern from
        `app/features/reporting/aggregations.py`). Advisors with no business records are
        absent from the result; callers default them to `(0, 0.0)`."""
        if not advisor_ids:
            return {}
        pipeline: list[dict[str, Any]] = [
            {"$match": {"advisor_id": {"$in": advisor_ids}, "is_deleted": False}},
            {"$group": {"_id": "$advisor_id", "count": {"$sum": 1}, "premium": {"$sum": "$premium"}}},
        ]
        return {
            doc["_id"]: (int(doc["count"]), float(doc["premium"]))
            async for doc in self.collection.aggregate(pipeline)
        }
