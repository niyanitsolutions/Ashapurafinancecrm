"""Read-only by default. Explicit target required; never merges/deletes identity data."""

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.features.auth.indexes import ensure_attendance_indexes
from app.features.auth.session_lifecycle import IDLE_TIMEOUT, ensure_summary
from app.shared.customer_identity import normalize_mobile, normalized_name
from app.utils.datetime import ensure_utc, ist_date_to_utc_midnight, to_ist, utc_now
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def inspect(db: AsyncIOMotorDatabase[Any]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "identity_conflicts": [],
        "noncanonical_mobile": [],
        "ambiguous_sessions": [],
        "families": 0,
    }
    for collection in ("leads", "customers"):
        identities: dict[str, list[str]] = {}
        async for doc in db[collection].find({"is_deleted": False}, {"mobile": 1}):
            try:
                canonical = normalize_mobile(doc.get("mobile"))
            except ValueError:
                canonical = None
            if canonical != doc.get("mobile") or canonical is None:
                report["noncanonical_mobile"].append(
                    {"collection": collection, "id": str(doc["_id"])}
                )
            if canonical:
                identities.setdefault(canonical, []).append(str(doc["_id"]))
        for ids in identities.values():
            if len(ids) > 1:
                report["identity_conflicts"].append(
                    {"collection": collection, "ids": ids}
                )
    async for family in db.sessions.aggregate(
        [
            {"$match": {"is_deleted": False}},
            {"$sort": {"updated_at": 1, "_id": 1}},
            {
                "$group": {
                    "_id": "$family_id",
                    "user_id": {"$first": "$user_id"},
                    "login_values": {"$addToSet": "$login_at"},
                    "user_values": {"$addToSet": "$user_id"},
                    "login_at": {"$min": "$login_at"},
                    "logout_at": {"$max": "$logout_at"},
                    "status": {"$last": "$status"},
                    "last_activity_at": {"$max": "$last_activity_at"},
                }
            },
        ]
    ):
        report["families"] += 1
        if (
            not family.get("_id")
            or not family.get("user_id")
            or len(family["login_values"]) != 1
            or len(family["user_values"]) != 1
            or not family.get("login_at")
            or not family.get("last_activity_at")
            or (family["status"] != "active" and not family.get("logout_at"))
            or (family.get("logout_at") and family["logout_at"] < family["login_at"])
        ):
            report["ambiguous_sessions"].append(str(family["_id"]))
    return report


async def apply(db: AsyncIOMotorDatabase[Any], report: dict[str, Any]) -> None:
    if any(
        report[key]
        for key in ("identity_conflicts", "noncanonical_mobile", "ambiguous_sessions")
    ):
        raise ValueError(
            "Review reported records first. No data or indexes were changed."
        )
    # New stronger indexes coexist with the old active-only index; no gap in protection.
    for collection in ("leads", "customers"):
        await db[collection].create_index(
            "mobile",
            name="identity_mobile_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        )
    async for lead in db.leads.find({"is_deleted": False}, {"full_name": 1}):
        await db.leads.update_one(
            {"_id": lead["_id"]},
            {"$set": {"identity_name": normalized_name(lead.get("full_name", ""))}},
        )
    await db.leads.create_index("identity_name")
    await ensure_attendance_indexes(db)
    async for correction in db.session_corrections.find({}):
        original = await db.sessions.find_one(
            {"family_id": correction["_id"], "is_deleted": False}, {"user_id": 1}
        )
        if not original:
            continue
        await db.session_corrections.update_one(
            {"_id": correction["_id"]}, {"$set": {"user_id": original["user_id"]}}
        )
        day = to_ist(correction["login_at"]).date()
        while day <= to_ist(correction["logout_at"]).date():
            await ensure_summary(db, original["user_id"], ist_date_to_utc_midnight(day))
            day += timedelta(days=1)
    async for doc in db.sessions.aggregate(
        [
            {"$match": {"is_deleted": False}},
            {"$sort": {"updated_at": 1, "_id": 1}},
            {
                "$group": {
                    "_id": "$family_id",
                    "user_id": {"$first": "$user_id"},
                    "login_at": {"$min": "$login_at"},
                    "logout_at": {"$max": "$logout_at"},
                    "last_activity_at": {"$max": "$last_activity_at"},
                }
            },
        ]
    ):
        login = ensure_utc(doc["login_at"])
        finish = (
            ensure_utc(doc["logout_at"])
            if doc.get("logout_at")
            else min(utc_now(), ensure_utc(doc["last_activity_at"]) + IDLE_TIMEOUT)
        )
        day = to_ist(login).date()
        while day <= to_ist(finish).date():
            await ensure_summary(db, doc["user_id"], ist_date_to_utc_midnight(day))
            day += timedelta(days=1)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    client: AsyncIOMotorClient[Any] = AsyncIOMotorClient(args.uri, tz_aware=True)
    try:
        db = client[args.database]
        report = await inspect(db)
        print(
            json.dumps(report, indent=2)
        )  # IDs only: no names, phone numbers or tokens.
        if args.apply:
            await apply(db, report)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
