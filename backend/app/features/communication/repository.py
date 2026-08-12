from datetime import datetime
from typing import Any

from app.features.communication.constants import QueueStatus
from app.features.communication.models import (
    CommunicationCheckpoint,
    CommunicationHistory,
    CommunicationPreference,
    CommunicationQueueItem,
    CommunicationTemplate,
    ProviderDeliveryLog,
)
from app.shared.base_repository import BaseRepository


class CommunicationTemplateRepository(BaseRepository[CommunicationTemplate]):
    collection_name = "communication_templates"
    model = CommunicationTemplate

    async def find_active_by_category_and_channel(self, *, category: str, channel: str) -> CommunicationTemplate | None:
        doc = await self.collection.find_one({"category": category, "channel": channel, "status": "active", "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self, *, channel: str | None, category: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationTemplate], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if channel:
            query["channel"] = channel
        if category:
            query["category"] = category
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class CommunicationQueueRepository(BaseRepository[CommunicationQueueItem]):
    collection_name = "communication_queue"
    model = CommunicationQueueItem

    async def find_due_pending(self, *, limit: int = 100) -> list[CommunicationQueueItem]:
        return await self.find_many({"status": QueueStatus.PENDING}, limit=limit, sort=[("created_at", 1)])

    async def find_due_for_retry(self, *, now: datetime, limit: int = 100) -> list[CommunicationQueueItem]:
        query = {"is_deleted": False, "status": QueueStatus.RETRYING, "next_retry_at": {"$lte": now}}
        return await self.find_many(query, limit=limit, sort=[("next_retry_at", 1)])

    async def search_and_filter(
        self, *, status: str | None, channel: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationQueueItem], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if status:
            query["status"] = status
        if channel:
            query["channel"] = channel
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_existing_for_event(self, *, business_event: str, entity_type: str, entity_id: str, channel: str) -> CommunicationQueueItem | None:
        doc = await self.collection.find_one(
            {"business_event": business_event, "entity_type": entity_type, "entity_id": entity_id, "channel": channel, "is_deleted": False}
        )
        return self.model.model_validate(doc) if doc else None


class CommunicationHistoryRepository(BaseRepository[CommunicationHistory]):
    collection_name = "communication_history"
    model = CommunicationHistory

    async def find_by_queue_item(self, queue_item_id: str) -> CommunicationHistory | None:
        doc = await self.collection.find_one({"queue_item_id": queue_item_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def search_and_filter(
        self, *, status: str | None, channel: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationHistory], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if status:
            query["status"] = status
        if channel:
            query["channel"] = channel
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total


class ProviderDeliveryLogRepository(BaseRepository[ProviderDeliveryLog]):
    collection_name = "provider_delivery_logs"
    model = ProviderDeliveryLog

    async def list_for_queue_item(self, queue_item_id: str) -> list[ProviderDeliveryLog]:
        return await self.find_many({"queue_item_id": queue_item_id}, limit=50, sort=[("attempt_number", 1)])


class CommunicationPreferenceRepository(BaseRepository[CommunicationPreference]):
    collection_name = "communication_preferences"
    model = CommunicationPreference

    async def find_by_user_id(self, user_id: str) -> CommunicationPreference | None:
        doc = await self.collection.find_one({"user_id": user_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None


class CommunicationCheckpointRepository(BaseRepository[CommunicationCheckpoint]):
    collection_name = "communication_checkpoints"
    model = CommunicationCheckpoint

    async def get_last_processed_at(self, business_event: str) -> datetime | None:
        doc = await self.collection.find_one({"business_event": business_event})
        return self.model.model_validate(doc).last_processed_at if doc else None

    async def set_last_processed_at(self, business_event: str, when: datetime) -> None:
        await self.collection.update_one({"business_event": business_event}, {"$set": {"business_event": business_event, "last_processed_at": when}}, upsert=True)
