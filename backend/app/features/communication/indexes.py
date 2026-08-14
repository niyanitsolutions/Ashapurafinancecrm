from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_communication_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["communication_templates"].create_index([("category", 1), ("channel", 1), ("status", 1)])
    await db["communication_queue"].create_index([("status", 1), ("created_at", 1)])
    await db["communication_queue"].create_index([("status", 1), ("next_retry_at", 1)])
    await db["communication_queue"].create_index([("business_event", 1), ("entity_type", 1), ("entity_id", 1), ("channel", 1)])
    await db["communication_queue"].create_index("provider_message_id")
    await db["communication_queue"].create_index([("entity_type", 1), ("entity_id", 1)])
    await db["bulk_message_jobs"].create_index("status")
    await db["communication_history"].create_index("queue_item_id", unique=True)
    await db["provider_delivery_logs"].create_index("queue_item_id")
    await db["communication_checkpoints"].create_index("business_event", unique=True)
    await db["communication_preferences"].create_index("user_id", unique=True)
