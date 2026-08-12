from app.features.reporting.models import ReportDefinition, SavedFilter, ScheduledReport
from app.shared.base_repository import BaseRepository


class ReportDefinitionRepository(BaseRepository[ReportDefinition]):
    collection_name = "report_definitions"
    model = ReportDefinition

    async def find_by_key(self, key: str) -> ReportDefinition | None:
        doc = await self.collection.find_one({"key": key, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def list_all(self) -> list[ReportDefinition]:
        return await self.find_many({}, limit=200, sort=[("category", 1), ("label", 1)])


class SavedFilterRepository(BaseRepository[SavedFilter]):
    collection_name = "saved_filters"
    model = SavedFilter

    async def find_for_user(self, user_id: str, *, report_key: str | None = None) -> list[SavedFilter]:
        query: dict[str, str] = {"user_id": user_id}
        if report_key:
            query["report_key"] = report_key
        return await self.find_many(query, limit=200, sort=[("created_at", -1)])


class ScheduledReportRepository(BaseRepository[ScheduledReport]):
    collection_name = "scheduled_reports"
    model = ScheduledReport
