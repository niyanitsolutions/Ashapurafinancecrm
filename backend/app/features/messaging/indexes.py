from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_messaging_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["conversations"].create_index("customer_id", unique=True)
    await db["conversations"].create_index("employee_id")
    await db["conversation_messages"].create_index("conversation_id")
