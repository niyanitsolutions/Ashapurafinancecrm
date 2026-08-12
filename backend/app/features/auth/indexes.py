"""Index definitions for collections this module owns/writes. Called once at app
startup (see main.py lifespan) — `create_index` is idempotent, safe to call every boot.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_auth_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["users"].create_index("mobile", unique=True)
    # DB-level "only one Owner ever" guarantee (see app/features/owner/service.py's
    # application-code pre-check, which this backs up under a race) — a partial unique
    # index, not a full one, since it must never constrain Employee/Customer/Referral
    # Partner rows sharing the same `role` field.
    await db["users"].create_index(
        "role", unique=True, partialFilterExpression={"role": "owner", "is_deleted": False}
    )

    await db["sessions"].create_index("token_id", unique=True)
    await db["sessions"].create_index("user_id")
    await db["sessions"].create_index("family_id")

    await db["audit_logs"].create_index("user_id")
    await db["audit_logs"].create_index("mobile")
    await db["audit_logs"].create_index("created_at")
