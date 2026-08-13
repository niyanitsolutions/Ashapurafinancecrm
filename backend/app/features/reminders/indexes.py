from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_reminders_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["tasks"].create_index("assigned_to")
    await db["tasks"].create_index("status")
    await db["tasks"].create_index("due_at")
    await db["tasks"].create_index([("related_entity_type", 1), ("related_entity_id", 1)])

    await db["reminder_rules"].create_index("rule_type")

    await db["reminders"].create_index([("target_type", 1), ("target_id", 1), ("reminder_type", 1)])
    await db["reminders"].create_index("status")

    await db["notifications"].create_index([("recipient_user_id", 1), ("status", 1)])
    await db["notifications"].create_index("created_at")

    await db["notification_checkpoints"].create_index("event_type", unique=True)
