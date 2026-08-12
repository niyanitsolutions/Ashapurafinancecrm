from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_lead_capture_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["capture_sources"].create_index("key", unique=True)
    await db["capture_failures"].create_index([("status", 1), ("next_retry_at", 1)])
    await db["capture_failures"].create_index("capture_source")
    await db["capture_receipts"].create_index([("capture_source", 1), ("external_id", 1)], unique=True)
