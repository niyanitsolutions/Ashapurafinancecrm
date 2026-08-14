from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_geo_fencing_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["geo_fences"].create_index("status")
    await db["geo_fences"].create_index("allowed_activities")
    await db["geo_fences"].create_index("area_name")
