from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_referral_partner_management_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["referral_partners"].create_index("user_id", unique=True)
    await db["referral_partners"].create_index("approval_status")

    await db["referral_leads"].create_index("lead_id", unique=True)
    await db["referral_leads"].create_index("partner_id")

    await db["commission_rules"].create_index([("product_category", 1), ("partner_id", 1)])

    await db["commission_entries"].create_index("case_id", unique=True)
    await db["commission_entries"].create_index([("partner_id", 1), ("status", 1)])
