from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_bin_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["bin_entries"].create_index([("target_collection", 1), ("document_id", 1)])
    await db["bin_entries"].create_index("resource_key")
    await db["bin_entries"].create_index("deleted_at")
    # Purge-scan support: the daily job filters restored_at/purged_at null + purge_at due.
    await db["bin_entries"].create_index([("restored_at", 1), ("purged_at", 1), ("purge_at", 1)])
