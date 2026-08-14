from typing import Any

from app.features.geo_fencing.constants import GeoFenceStatus
from app.features.geo_fencing.models import GeoFence
from app.shared.base_repository import BaseRepository


class GeoFenceRepository(BaseRepository[GeoFence]):
    collection_name = "geo_fences"
    model = GeoFence

    async def search_and_filter(
        self, *, search: str | None, activity: str | None, status: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[GeoFence], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if search:
            query["$or"] = [
                {"area_name": {"$regex": search, "$options": "i"}},
                {"address": {"$regex": search, "$options": "i"}},
            ]
        if activity:
            query["allowed_activities"] = activity
        if status:
            query["status"] = status
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_active_for_activity(self, activity: str) -> list[GeoFence]:
        return await self.find_many({"status": GeoFenceStatus.ACTIVE, "allowed_activities": activity}, limit=200)

    async def find_all_active(self) -> list[GeoFence]:
        return await self.find_many({"status": GeoFenceStatus.ACTIVE}, limit=1000)
