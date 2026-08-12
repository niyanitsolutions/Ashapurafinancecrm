from datetime import datetime
from typing import Any

from app.features.lead_capture.constants import FailureStatus
from app.features.lead_capture.models import CaptureFailure, CaptureReceipt, CaptureSource
from app.shared.base_repository import BaseRepository


class CaptureSourceRepository(BaseRepository[CaptureSource]):
    collection_name = "capture_sources"
    model = CaptureSource

    async def find_by_key(self, key: str) -> CaptureSource | None:
        doc = await self.collection.find_one({"key": key, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def list_all(self) -> list[CaptureSource]:
        return await self.find_many({}, limit=50, sort=[("key", 1)])


class CaptureFailureRepository(BaseRepository[CaptureFailure]):
    collection_name = "capture_failures"
    model = CaptureFailure

    async def search_and_filter(
        self, *, capture_source: str | None, status: str | None, failure_reason: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CaptureFailure], int]:
        query: dict[str, Any] = {"is_deleted": False}
        if capture_source:
            query["capture_source"] = capture_source
        if status:
            query["status"] = status
        if failure_reason:
            query["failure_reason"] = failure_reason
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        items = [self.model.model_validate(doc) async for doc in cursor]
        return items, total

    async def find_due_for_retry(self, *, now: datetime, limit: int = 100) -> list[CaptureFailure]:
        query = {"is_deleted": False, "status": FailureStatus.PENDING, "next_retry_at": {"$lte": now}}
        return await self.find_many(query, limit=limit, sort=[("next_retry_at", 1)])


class CaptureReceiptRepository(BaseRepository[CaptureReceipt]):
    collection_name = "capture_receipts"
    model = CaptureReceipt

    async def find_existing(self, capture_source: str, external_id: str) -> CaptureReceipt | None:
        doc = await self.collection.find_one({"capture_source": capture_source, "external_id": external_id, "is_deleted": False})
        return self.model.model_validate(doc) if doc else None

    async def find_latest_for_source(self, capture_source: str) -> CaptureReceipt | None:
        results = await self.find_many({"capture_source": capture_source}, limit=1, sort=[("created_at", -1)])
        return results[0] if results else None

    async def count_for_source(self, capture_source: str) -> int:
        return await self.count({"capture_source": capture_source})
