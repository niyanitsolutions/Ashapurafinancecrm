"""Index definitions for collections this module owns. Called once at app startup (see
main.py lifespan) — create_index is idempotent, safe to call every boot.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_employee_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["employees"].create_index("user_id", unique=True)
    await db["employees"].create_index("employee_code", unique=True)
    await db["employees"].create_index("email", unique=True)
    await db["employees"].create_index("department_id")
    await db["employees"].create_index("designation_id")
    await db["employees"].create_index("branch_id")
    await db["employees"].create_index("status")

    await db["departments"].create_index("name", unique=True)
    await db["designations"].create_index("name", unique=True)
    await db["branches"].create_index("code", unique=True)

    await db["employee_documents"].create_index("employee_id")
