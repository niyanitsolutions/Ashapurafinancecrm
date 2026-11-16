from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_integrations_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["integration_providers"].create_index(
        [("integration_type", 1), ("provider", 1)], unique=True
    )
    await db["integration_configs"].create_index("integration_type")
    await db["integration_configs"].create_index([("integration_type", 1), ("is_active", 1)])
    await db["integration_test_logs"].create_index("config_id")
    await db.integration_airtel_test_otps.create_index("expires_at", expireAfterSeconds=0)

    from app.features.integrations.airtel_iq import ensure_provider

    await ensure_provider(db)
