"""Module 8 — the Aggregation Layer. Every report definition in `reports.py` builds on
these few generic helpers instead of hand-writing its own Mongo pipeline — the same
"a handful of generic primitives, many thin call sites" shape as `shared/base_repository.py`.
Every helper reads a frozen module's collection directly (never writes), the same
read-only-reuse pattern used by every report-consuming module since 6C.
"""

from datetime import date
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.datetime import ist_date_range_to_utc_bounds

_NOT_DELETED: dict[str, Any] = {"is_deleted": False}


def date_range_match(date_field: str, date_from: date | None, date_to: date | None) -> dict[str, Any]:
    """`date_from`/`date_to` are business (IST) calendar dates, inclusive both ends, as
    picked by a user in a report filter — converted to the equivalent UTC instant
    bounds (`ist_date_range_to_utc_bounds`) before querying, since stored timestamps are
    UTC. Previously combined the bare calendar dates with `time.min`/`time.max` with no
    timezone applied at all, which filtered on UTC midnight-to-midnight instead of the
    IST business day the user actually selected."""
    lower, upper = ist_date_range_to_utc_bounds(date_from, date_to)
    range_query: dict[str, Any] = {}
    if lower is not None:
        range_query["$gte"] = lower
    if upper is not None:
        range_query["$lt"] = upper
    return {date_field: range_query} if range_query else {}


async def group_count(
    db: AsyncIOMotorDatabase[Any], collection: str, *, group_field: str, date_field: str, date_from: date | None, date_to: date | None,
    extra_match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    match: dict[str, Any] = {**_NOT_DELETED, **date_range_match(date_field, date_from, date_to), **(extra_match or {})}
    pipeline = [{"$match": match}, {"$group": {"_id": f"${group_field}", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    return [{"group_value": doc["_id"], "count": doc["count"]} async for doc in db[collection].aggregate(pipeline)]


async def group_sum(
    db: AsyncIOMotorDatabase[Any], collection: str, *, group_field: str, sum_field: str, date_field: str, date_from: date | None, date_to: date | None,
    extra_match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    match: dict[str, Any] = {**_NOT_DELETED, **date_range_match(date_field, date_from, date_to), **(extra_match or {})}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": f"${group_field}", "count": {"$sum": 1}, "total": {"$sum": f"${sum_field}"}}},
        {"$sort": {"total": -1}},
    ]
    return [{"group_value": doc["_id"], "count": doc["count"], "total": doc["total"]} async for doc in db[collection].aggregate(pipeline)]


async def count_matching(
    db: AsyncIOMotorDatabase[Any], collection: str, *, date_field: str, date_from: date | None, date_to: date | None, extra_match: dict[str, Any] | None = None
) -> int:
    match: dict[str, Any] = {**_NOT_DELETED, **date_range_match(date_field, date_from, date_to), **(extra_match or {})}
    return await db[collection].count_documents(match)


async def resolve_names(db: AsyncIOMotorDatabase[Any], collection: str, ids: set[str], *, name_field: str = "name") -> dict[str, str]:
    """Resolves a set of stringified ObjectIds to a display name — `name` for the usual
    named-master-data collections, `display_name`/`full_name`/`label` etc. for others.
    `None`/missing ids are simply absent from the returned dict; callers fall back to a
    placeholder (e.g. "Unassigned") themselves, since that fallback text is report-specific.
    """
    object_ids = [ObjectId(i) for i in ids if i]
    if not object_ids:
        return {}
    cursor = db[collection].find({"_id": {"$in": object_ids}}, {name_field: 1})
    return {str(doc["_id"]): doc[name_field] async for doc in cursor if name_field in doc}
