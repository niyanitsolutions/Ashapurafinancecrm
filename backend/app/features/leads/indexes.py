from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_lead_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    from app.features.leads.auto_assignment import ensure_assignment_indexes

    await ensure_assignment_indexes(db)
    await db["leads"].create_index("lead_code", unique=True)
    await db["leads"].create_index("mobile")
    await db.leads.create_index("identity_name")
    await db.leads.create_index("intake_key", unique=True, partialFilterExpression={"intake_key": {"$type": "string"}})
    await db["leads"].create_index("assigned_to")
    await db["leads"].create_index("source_id")
    await db["leads"].create_index("product_category")
    await db["leads"].create_index("status")
    await db["leads"].create_index("stage")
    await db["leads"].create_index([("assigned_to", 1), ("stage", 1)])
    await db["leads"].create_index("next_follow_up_date")

    await db["lead_notes"].create_index("lead_id")
    await db["lead_activities"].create_index("lead_id")
