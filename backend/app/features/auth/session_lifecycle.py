"""Refresh rows remain the authority; a family is one human login session."""

from datetime import datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import UnauthorizedError
from app.utils.datetime import ensure_utc, to_ist, utc_now

IDLE_TIMEOUT = timedelta(minutes=10)


async def ensure_summary(db: AsyncIOMotorDatabase[Any], user_id: str, now: datetime) -> str:
    day = to_ist(now).date().isoformat()
    key = f"{user_id}:{day}"
    try:
        await db.attendance_days.update_one(
            {"_id": key},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "date": day,
                    "created_at": now,
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        pass  # Another request inserted the same deterministic employee/date key.
    return key


async def expire_sessions(db: AsyncIOMotorDatabase[Any], limit: int = 500) -> int:
    now = utc_now()
    count = 0
    async for doc in (
        db.sessions.find(
            {
                "status": "active",
                "is_deleted": False,
                "last_activity_at": {"$lte": now - IDLE_TIMEOUT},
            }
        )
        .sort("last_activity_at", 1)
        .limit(limit)
    ):
        end = ensure_utc(doc["last_activity_at"]) + IDLE_TIMEOUT
        result = await db.sessions.update_one(
            {"_id": doc["_id"], "status": "active", "last_activity_at": doc["last_activity_at"]},
            {
                "$set": {
                    "status": "logged_out",
                    "logout_at": end,
                    "end_reason": "inactivity_timeout",
                    "updated_at": now,
                },
                "$inc": {"version": 1},
                "$push": {
                    "lifecycle_history": {
                        "at": now,
                        "from_status": "active",
                        "to_status": "logged_out",
                        "source": "automatic",
                        "end_reason": "inactivity_timeout",
                        "end_at": end,
                    }
                },
            },
        )
        if result.modified_count:
            await ensure_summary(db, doc["user_id"], end - timedelta(microseconds=1))
        count += result.modified_count
    async for receipt in db.sessions.find(
        {
            "login_at": {"$lt": now - timedelta(minutes=2)},
            "login_response_encrypted": {"$exists": True},
        },
        {"_id": 1},
    ).limit(limit):
        await db.sessions.update_one(
            {"_id": receipt["_id"]}, {"$unset": {"login_response_encrypted": ""}}
        )
    return count


async def validate_family(
    db: AsyncIOMotorDatabase[Any],
    user_id: str,
    family_id: str,
    *,
    activity: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    if await db.sessions.find_one(
        {
            "user_id": user_id,
            "family_id": family_id,
            "status": {"$in": ["revoked", "logged_out"]},
            "is_deleted": False,
        },
        {"_id": 1},
    ):
        raise UnauthorizedError("Session expired or revoked. Please login again.")
    query = {
        "user_id": user_id,
        "family_id": family_id,
        "status": "active",
        "is_deleted": False,
        "last_activity_at": {"$gt": now - IDLE_TIMEOUT},
    }
    if activity:
        doc = await db.sessions.find_one_and_update(
            query,
            {"$max": {"last_activity_at": now}},
            return_document=ReturnDocument.AFTER,
        )
    else:
        doc = await db.sessions.find_one(query)
    if not doc:
        # Finalize only this family. Never let an expired family extend another device.
        async for stale in db.sessions.find(
            {"user_id": user_id, "family_id": family_id, "status": "active", "is_deleted": False}
        ):
            result = await db.sessions.update_one(
                {
                    "_id": stale["_id"],
                    "status": "active",
                    "last_activity_at": stale["last_activity_at"],
                },
                {
                    "$set": {
                        "status": "logged_out",
                        "end_reason": "inactivity_timeout",
                        "logout_at": ensure_utc(stale["last_activity_at"]) + IDLE_TIMEOUT,
                        "updated_at": now,
                    },
                    "$inc": {"version": 1},
                    "$push": {
                        "lifecycle_history": {
                            "at": now,
                            "from_status": "active",
                            "to_status": "logged_out",
                            "source": "automatic",
                            "end_reason": "inactivity_timeout",
                        }
                    },
                },
            )
            if result.modified_count:
                await ensure_summary(
                    db,
                    user_id,
                    ensure_utc(stale["last_activity_at"])
                    + IDLE_TIMEOUT
                    - timedelta(microseconds=1),
                )
        raise UnauthorizedError("Session expired or revoked. Please login again.")
    await ensure_summary(db, user_id, now)
    return dict(doc)
