from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_owner_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["owner_profiles"].create_index("email", unique=True)
