from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.owner.constants import OwnerType


async def ensure_owner_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    # Idempotent backfill for Owner Account Management: any owner_profiles document
    # written before `owner_type` existed (when at most one Owner could ever exist) is,
    # by definition, that sole existing Owner — i.e. Primary. The model's Pydantic
    # default already reads such a document as PRIMARY, but a partial unique index only
    # sees fields actually stored on disk (see the index below), so the field must be
    # physically backfilled too. No-op on every run after the first.
    await db["owner_profiles"].update_many(
        {"owner_type": {"$exists": False}}, {"$set": {"owner_type": OwnerType.PRIMARY}}
    )

    await db["owner_profiles"].create_index("email", unique=True)
    await db["owner_profiles"].create_index("user_id", unique=True)
    # DB-level "exactly one Primary Owner ever" guarantee — the multi-Owner equivalent of
    # the old `users.role="owner"` partial unique index this superseded (see
    # auth/indexes.py). Partial, not full, since it must never constrain the (unlimited)
    # Secondary Owner documents sharing this same collection.
    await db["owner_profiles"].create_index(
        "owner_type", unique=True, partialFilterExpression={"owner_type": OwnerType.PRIMARY, "is_deleted": False}
    )
