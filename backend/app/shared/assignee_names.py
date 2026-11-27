"""Owner self-assignment uses the existing Owner User ID; never create a fake Employee."""

from typing import Any

from bson import ObjectId


async def owner_names(db: Any, ids: set[str]) -> dict[str, str]:
    valid = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    if not valid:
        return {}
    owners = [
        str(u["_id"])
        async for u in db.users.find(
            {"_id": {"$in": valid}, "role": "owner", "is_deleted": False}, {"_id": 1}
        )
    ]
    names = {
        r["user_id"]: r["full_name"]
        async for r in db.owner_profiles.find(
            {"user_id": {"$in": owners}, "is_deleted": False}, {"user_id": 1, "full_name": 1}
        )
    }
    return {uid: names.get(uid, "Owner") for uid in owners}
