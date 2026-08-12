"""Index definitions for collections this module owns/writes. Called once at app
startup (see main.py lifespan) — `create_index` is idempotent, safe to call every boot.
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_auth_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db["users"].create_index("mobile", unique=True)

    # Historical: a partial unique index on role="owner" used to enforce "at most one
    # Owner ever" at the DB level. Superseded by Owner Account Management (Primary +
    # Secondary Owners, both role="owner") — that invariant now lives on
    # owner_profiles.owner_type="primary" instead (see owner/indexes.py), since this
    # collection has no way to distinguish the two. Dropped idempotently: a no-op once
    # already removed, and harmless on a fresh install that never created it.
    existing_indexes = await db["users"].index_information()
    if "role_1" in existing_indexes:
        await db["users"].drop_index("role_1")

    await db["sessions"].create_index("token_id", unique=True)
    await db["sessions"].create_index("user_id")
    await db["sessions"].create_index("family_id")

    await db["audit_logs"].create_index("user_id")
    await db["audit_logs"].create_index("mobile")
    await db["audit_logs"].create_index("created_at")
