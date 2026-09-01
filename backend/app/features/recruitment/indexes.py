from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_recruitment_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["recruitment_leads"].create_index("recruitment_code", unique=True)
    await db["recruitment_leads"].create_index("mobile")
    await db["recruitment_leads"].create_index("stage")
    await db["recruitment_leads"].create_index("assigned_to")
    await db["recruitment_leads"].create_index("created_by")
    await db["recruitment_leads"].create_index([("stage", 1), ("assigned_to", 1)])

    await db["recruitment_activities"].create_index("recruitment_lead_id")
    await db["recruitment_notes"].create_index("recruitment_lead_id")

    await db["advisors"].create_index("advisor_code", unique=True)
    await db["advisors"].create_index("recruitment_lead_id", unique=True)
    await db["advisors"].create_index("channel")
    await db["advisors"].create_index("status")

    await db["advisor_business"].create_index("advisor_id")
