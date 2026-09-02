from typing import Any

from app.features.bin.models import BinEntry
from app.shared.base_repository import BaseRepository


class BinEntryRepository(BaseRepository[BinEntry]):
    collection_name = "bin_entries"
    model = BinEntry

    async def find_active_for_document(self, target_collection: str, document_id: str) -> BinEntry | None:
        doc = await self.collection.find_one(
            {"target_collection": target_collection, "document_id": document_id, "restored_at": None, "purged_at": None}
        )
        return self.model.model_validate(doc) if doc else None

    async def list_active(
        self, *, resource_key: str | None, search: str | None, skip: int, limit: int
    ) -> tuple[list[BinEntry], int]:
        query: dict[str, Any] = {"restored_at": None, "purged_at": None}
        if resource_key:
            query["resource_key"] = resource_key
        if search:
            import re

            rx = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [{"record_code": rx}, {"record_summary": rx}]
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("deleted_at", -1).skip(skip).limit(limit)
        return [self.model.model_validate(d) async for d in cursor], total

    async def find_due_for_purge(self, now: Any, *, limit: int = 500) -> list[BinEntry]:
        cursor = self.collection.find({"restored_at": None, "purged_at": None, "purge_at": {"$lte": now}}).limit(limit)
        return [self.model.model_validate(d) async for d in cursor]
