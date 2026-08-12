"""Index definitions for collections this module owns. Departments/designations/branches
already get their unique indexes from Module 2's `ensure_employee_indexes` (frozen) —
not repeated here. Called once at app startup; `create_index` is idempotent."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_system_settings_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["lead_sources"].create_index("name", unique=True)
    await db["loan_products"].create_index("name", unique=True)
    await db["insurance_products"].create_index("name", unique=True)
    await db["document_types"].create_index("name", unique=True)
    await db["status_masters"].create_index([("category", 1), ("name", 1)], unique=True)
    await db["notification_templates"].create_index([("channel", 1), ("key", 1)], unique=True)
    await db["api_settings"].create_index([("provider", 1), ("label", 1)], unique=True)
    await db["company_settings"].create_index("singleton_key", unique=True)
