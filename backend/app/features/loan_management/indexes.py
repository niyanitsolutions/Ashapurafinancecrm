from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_loan_management_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["loan_case_bank_offers"].create_index("loan_case_id")
