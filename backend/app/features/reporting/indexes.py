from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_reporting_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["report_definitions"].create_index("key", unique=True)
    await db["saved_filters"].create_index([("user_id", 1), ("report_key", 1)])
    await db["scheduled_reports"].create_index("report_key")
