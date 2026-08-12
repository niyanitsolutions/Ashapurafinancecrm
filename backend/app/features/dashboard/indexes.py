from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_dashboard_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["dashboard_widgets"].create_index("key", unique=True)
    await db["dashboard_layout_preferences"].create_index([("user_id", 1), ("widget_key", 1)], unique=True)
    await db["nav_items"].create_index("key", unique=True)
