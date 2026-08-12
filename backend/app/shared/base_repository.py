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
