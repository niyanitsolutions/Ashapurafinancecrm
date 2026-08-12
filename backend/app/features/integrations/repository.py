from typing import Any

from app.features.integrations.models import (
    IntegrationConfig,
    IntegrationProvider,
    IntegrationTestLog,
)
from app.shared.base_repository import BaseRepository
from app.utils.helpers import to_object_id


class IntegrationProviderRepository(BaseRepository[IntegrationProvider]):
    collection_name = "integration_providers"
    model = IntegrationProvider

    async def list_all(self) -> list[IntegrationProvider]:
        return await self.find_many({}, limit=200, sort=[("integration_type", 1), ("label", 1)])

    async def find_by_type_and_provider(self, integration_type: str, provider: str) -> IntegrationProvider | None:
        doc = await self.collection.find_one({"integration_type": integration_type, "provider": provider, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class IntegrationConfigRepository(BaseRepository[IntegrationConfig]):
    collection_name = "integration_configs"
    model = IntegrationConfig

    async def search_and_filter(
        self, *, integration_type: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[IntegrationConfig], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if integration_type:
            query["integration_type"] = integration_type
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def deactivate_others(self, integration_type: str, *, exclude_id: str) -> None:
        await self.collection.update_many(
            {"integration_type": integration_type, "is_deleted": False, "_id": {"$ne": to_object_id(exclude_id)}}, {"$set": {"is_active": False}}
        )


class IntegrationTestLogRepository(BaseRepository[IntegrationTestLog]):
    collection_name = "integration_test_logs"
    model = IntegrationTestLog

    async def find_for_config(self, config_id: str, *, limit: int = 20) -> list[IntegrationTestLog]:
        # `_id` as a tiebreaker — see SecureLinkRepository.find_latest_for_lead's own
        # comment: BSON datetime is millisecond-precision, so two test-connection calls
        # fired in quick succession can share an identical `tested_at`.
        return await self.find_many({"config_id": config_id}, limit=limit, sort=[("tested_at", -1), ("_id", -1)])
