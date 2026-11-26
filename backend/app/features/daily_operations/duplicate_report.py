"""Bounded read-only preflight. Never installs indexes, merges or rewrites records."""

from typing import Any

from app.core.exceptions import ForbiddenError
from app.shared.customer_identity import normalize_mobile


async def preview(db: Any, actor: Any) -> dict[str, Any]:
    if actor.role != "owner":
        raise ForbiddenError("Owner identity review is required.")
    groups = await db.daily_follow_ups.aggregate(
        [
            {"$match": {"application_id": {"$type": "string"}}},
            {
                "$group": {
                    "_id": "$application_id",
                    "record_ids": {"$push": {"$toString": "$_id"}},
                    "count": {"$sum": 1},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"_id": 1}},
            {"$limit": 101},
        ]
    ).to_list(101)
    identities: dict[str, list[str]] = {}
    invalid = []
    count = 0
    async for row in db.users.find({}, {"mobile": 1}).sort("_id", 1).limit(10001):
        count += 1
        if count > 10000:
            break
        try:
            key = normalize_mobile(row.get("mobile"))
            identities.setdefault(key, []).append(str(row["_id"]))
        except ValueError:
            invalid.append(str(row["_id"]))
    return {
        "mode": "read_only",
        "application_duplicates": [
            {"application_id": g["_id"], "record_ids": g["record_ids"], "count": g["count"]}
            for g in groups[:100]
        ],
        "application_groups_truncated": len(groups) > 100,
        "identity_conflicts": [ids for ids in identities.values() if len(ids) > 1],
        "invalid_mobile_user_ids": invalid,
        "users_truncated": count > 10000,
        "action": "Owner-approved individual resolution required; no indexes or records changed.",
    }
