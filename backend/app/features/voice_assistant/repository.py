from typing import Any, cast

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, NotFoundError
from app.utils.datetime import utc_now


def public(document: dict[str, Any]) -> dict[str, Any]:
    return {
        ("id" if key == "_id" else key): str(value) if isinstance(value, ObjectId) else value
        for key, value in document.items()
    }


class VoiceRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def get(self, collection: str, record_id: str) -> dict[str, Any]:
        if not ObjectId.is_valid(record_id):
            raise NotFoundError("Voice record not found.")
        doc = await self.db[collection].find_one({"_id": ObjectId(record_id), "is_deleted": False})
        if doc is None:
            raise NotFoundError("Voice record not found.")
        return cast(dict[str, Any], doc)

    async def update(
        self,
        collection: str,
        doc: dict[str, Any],
        updates: dict[str, Any],
        actor_id: str,
        event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        change = {
            "$set": {**updates, "updated_at": utc_now(), "updated_by": actor_id},
            "$inc": {"version": 1},
        }
        if event:
            change["$push"] = {"timeline": event}
        try:
            result = await self.db[collection].find_one_and_update(
                {"_id": doc["_id"], "version": doc["version"], "is_deleted": False},
                change,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ConflictError("This content conflicts with an existing record.") from exc
        if result is None:
            raise ConflictError("The record changed. Refresh before retrying.")
        return cast(dict[str, Any], result)


async def ensure_voice_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_calls.create_index("idempotency_key", unique=True)
    await db.voice_calls.create_index([("owner_user_id", 1), ("created_at", -1)])
    await db.voice_calls.create_index([("status", 1), ("deadline_at", 1)])
    await db.voice_knowledge.create_index([("status", 1), ("language", 1)])
    await db.voice_knowledge.create_index(
        "content_hash",
        unique=True,
        partialFilterExpression={"is_deleted": False},
    )
    await db.voice_settings.create_index("singleton_key", unique=True)
    await db.voice_worker_health.create_index("singleton_key", unique=True)
    await db.voice_knowledge_evaluations.create_index([("article_id", 1), ("created_at", -1)])
