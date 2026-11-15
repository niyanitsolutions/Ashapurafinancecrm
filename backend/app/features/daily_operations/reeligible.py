"""Daily follow-up workflow on the existing record, using India business dates."""

from datetime import timedelta
from typing import Any

from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now

REELIGIBLE = "Re-Eligible"
HOLD = "CASE ON HOLD WITH REASON"
PRIORITIES = ["FOLLOW UP PENDING", "NEXT FOLLOW UP", HOLD, "DISBURSE", REELIGIBLE]


def is_reeligible(status: str, label: str | None = None) -> bool:
    return (label or status).strip().casefold().replace("-", " ") == "re eligible"


def priority_stage() -> dict[str, Any]:
    # Custom options retain their IDs; their saved labels carry display semantics.
    label = {"$toUpper": {"$ifNull": ["$status_label", "$status"]}}
    return {
        "$set": {
            "_status_priority": {
                "$switch": {
                    "branches": [
                        {
                            "case": {
                                "$in": [
                                    label,
                                    (
                                        [name.upper(), "RE ELIGIBLE"]
                                        if name == REELIGIBLE
                                        else [name.upper()]
                                    ),
                                ]
                            },
                            "then": rank,
                        }
                        for rank, name in enumerate(PRIORITIES)
                    ]
                    + [{"case": {"$eq": ["$status", "REJECTED WITH REASON"]}, "then": 100}],
                    "default": 50,
                }
            }
        }
    }


async def reconcile_reeligible(db: Any, limit: int = 500) -> int:
    now = utc_now()
    tomorrow = ist_date_to_utc_midnight(to_ist(now).date() + timedelta(days=1))
    query = {
        "is_deleted": False,
        "reeligible_state": "waiting",
        "reeligible_date": {"$ne": None, "$lt": tomorrow},
    }
    count = 0
    async for doc in db.daily_follow_ups.find(query).sort("_id", 1).limit(limit):
        if not is_reeligible(doc["status"], doc.get("status_label")):
            continue
        result = await db.daily_follow_ups.update_one(
            {
                **query,
                "_id": doc["_id"],
                "version": doc["version"],
                "status": doc["status"],
                "reeligible_date": doc["reeligible_date"],
            },
            {
                "$set": {
                    "reeligible_state": "ready",
                    "reeligible_transitioned_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
                "$push": {
                    "history": {
                        "source": "automatic",
                        "automatic": True,
                        "actor_id": None,
                        "at": now,
                        "business_date": to_ist(now).date().isoformat(),
                        "before": {
                            "reeligible_state": "waiting",
                            "reeligible_date": doc["reeligible_date"],
                        },
                        "after": {
                            "reeligible_state": "ready",
                            "reeligible_date": doc["reeligible_date"],
                        },
                    }
                },
            },
        )
        count += result.modified_count
    return count
