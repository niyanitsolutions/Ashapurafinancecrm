from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_integrations_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["integration_providers"].create_index([("integration_type", 1), ("provider", 1)], unique=True)
    await db["integration_configs"].create_index("integration_type")
    await db["integration_configs"].create_index([("integration_type", 1), ("is_active", 1)])
    await db["integration_test_logs"].create_index("config_id")
