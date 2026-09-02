"""Generic repository: centralizes soft-delete filtering and base-field stamping so
individual features never have to reimplement it (see docs/decisions/DECISIONS.md on why
this lives here rather than per-feature).
"""

from typing import Any, Generic, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.shared.base_document import BaseDocument
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id

TModel = TypeVar("TModel", bound=BaseDocument)

_NOT_DELETED: dict[str, Any] = {"is_deleted": False}


class BaseRepository(Generic[TModel]):
    """Subclass per feature, setting `collection_name` and `model`."""

    collection_name: str
    model: type[TModel]

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db

    @property
    def collection(self) -> AsyncIOMotorCollection[Any]:
        return self._db[self.collection_name]

    async def find_by_id(self, doc_id: str, *, include_deleted: bool = False) -> TModel | None:
        query: dict[str, Any] = {"_id": to_object_id(doc_id)}
        if not include_deleted:
            query.update(_NOT_DELETED)
        doc = await self.collection.find_one(query)
        return self.model.model_validate(doc) if doc else None

    async def find_many(
        self,
        filters: dict[str, Any] | None = None,
        *,
        skip: int = 0,
        limit: int = 20,
        sort: list[tuple[str, int]] | None = None,
        include_deleted: bool = False,
    ) -> list[TModel]:
        query = dict(filters or {})
        if not include_deleted:
            query.update(_NOT_DELETED)
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return [self.model.model_validate(doc) async for doc in cursor]

    async def count(self, filters: dict[str, Any] | None = None, *, include_deleted: bool = False) -> int:
        query = dict(filters or {})
        if not include_deleted:
            query.update(_NOT_DELETED)
        return await self.collection.count_documents(query)

    async def insert(self, document: TModel) -> str:
        payload = document.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(payload)
        return str(result.inserted_id)

    async def update(self, doc_id: str, updates: dict[str, Any], *, updated_by: str | None = None) -> TModel | None:
        doc = await self.collection.find_one_and_update(
            {"_id": to_object_id(doc_id), **_NOT_DELETED},
            {
                "$set": {**updates, "updated_at": utc_now(), "updated_by": updated_by},
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.model.model_validate(doc) if doc else None

    async def soft_delete(self, doc_id: str, *, deleted_by: str | None = None) -> bool:
        result = await self.collection.update_one(
            {"_id": to_object_id(doc_id), **_NOT_DELETED},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": utc_now(),
                    "deleted_by": deleted_by,
                    "status": "deleted",
                },
                "$inc": {"version": 1},
            },
        )
        return result.modified_count == 1

    async def soft_delete_many(self, doc_ids: list[str], *, deleted_by: str | None = None) -> list[str]:
        """Bulk soft-delete in a single write (used by the centralized Bin's bulk-delete —
        never an inefficient per-id loop). Returns the ids that were actually flipped
        (i.e. weren't already deleted)."""
        object_ids = [to_object_id(i) for i in doc_ids]
        not_yet_deleted = {
            str(doc["_id"]) async for doc in self.collection.find({"_id": {"$in": object_ids}, **_NOT_DELETED}, {"_id": 1})
        }
        if not not_yet_deleted:
            return []
        await self.collection.update_many(
            {"_id": {"$in": [to_object_id(i) for i in not_yet_deleted]}},
            {"$set": {"is_deleted": True, "deleted_at": utc_now(), "deleted_by": deleted_by, "status": "deleted"}, "$inc": {"version": 1}},
        )
        return [i for i in doc_ids if i in not_yet_deleted]

    async def restore(self, doc_id: str, *, restored_by: str | None = None, restore_status: str | None = None) -> bool:
        """Reverse of `soft_delete` — clears the soft-delete markers so the record
        reappears in every normal list. Only affects a currently-deleted row. The
        record's own domain state (a Lead's `stage`, a case's `current_status`, ...) was
        never touched by the delete. `soft_delete` overwrote the generic `status` field
        with "deleted"; `restore_status` (the value captured at delete time) is written
        back so a model with a constrained `status` (e.g. `Lead`) validates on read."""
        set_updates: dict[str, Any] = {
            "is_deleted": False, "deleted_at": None, "deleted_by": None, "updated_at": utc_now(), "updated_by": restored_by,
        }
        if restore_status is not None:
            set_updates["status"] = restore_status
        result = await self.collection.update_one(
            {"_id": to_object_id(doc_id), "is_deleted": True},
            {"$set": set_updates, "$inc": {"version": 1}},
        )
        return result.modified_count == 1
