from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_lead_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["leads"].create_index("lead_code", unique=True)
    await db["leads"].create_index("mobile")
    await db["leads"].create_index("assigned_to")
    await db["leads"].create_index("source_id")
    await db["leads"].create_index("product_category")
    await db["leads"].create_index("status")

    await db["lead_notes"].create_index("lead_id")
    await db["lead_activities"].create_index("lead_id")
