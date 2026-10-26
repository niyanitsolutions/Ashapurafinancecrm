"""Business-date projection plus idempotent, compare-and-set transition history."""

from datetime import datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now

OPEN = ["FOLLOW UP PENDING", "NEXT FOLLOW UP"]


def effective_status(status: str, due: datetime | None, now: datetime) -> str:
    if status not in OPEN or due is None:
        return status
    return OPEN[0] if to_ist(due).date() <= to_ist(now).date() else OPEN[1]


def status_stage(now: datetime) -> dict[str, Any]:
    tomorrow = ist_date_to_utc_midnight(to_ist(now).date() + timedelta(days=1))
    return {
        "$set": {
            "status": {
                "$cond": [
                    {
                        "$and": [
                            {"$in": ["$status", OPEN]},
                            {"$ne": [{"$ifNull": ["$due_date", None]}, None]},
                        ]
                    },
                    {"$cond": [{"$lt": ["$due_date", tomorrow]}, OPEN[0], OPEN[1]]},
                    "$status",
                ]
            }
        }
    }


async def reconcile_statuses(db: AsyncIOMotorDatabase[Any], limit: int = 500) -> int:
    now = utc_now()
    tomorrow = ist_date_to_utc_midnight(to_ist(now).date() + timedelta(days=1))
    query = {
        "is_deleted": False,
        "$or": [
            {"status": OPEN[1], "due_date": {"$ne": None, "$lt": tomorrow}},
            {"status": OPEN[0], "due_date": {"$gte": tomorrow}},
        ],
    }
    changed = 0
    async for doc in db.daily_follow_ups.find(query).sort("_id", 1).limit(limit):
        target = effective_status(doc["status"], doc.get("due_date"), now)
        result = await db.daily_follow_ups.update_one(
            {
                "_id": doc["_id"],
                "version": doc["version"],
                "status": doc["status"],
                "due_date": doc.get("due_date"),
                "is_deleted": False,
            },
            {
                "$set": {"status": target, "updated_at": now},
                "$inc": {"version": 1},
                "$push": {
                    "history": {
                        "actor_id": None,
                        "source": "automatic",
                        "at": now,
                        "before": {"status": doc["status"]},
                        "after": {"status": target},
                        "business_date": to_ist(now).date().isoformat(),
                    }
                },
            },
        )
        changed += result.modified_count
    return changed
