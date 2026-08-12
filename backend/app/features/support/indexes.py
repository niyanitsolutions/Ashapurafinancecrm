from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_support_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["support_tickets"].create_index("customer_id")
    await db["support_tickets"].create_index("created_at")
