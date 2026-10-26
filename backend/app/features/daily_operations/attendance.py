"""Daily attendance projections over the original refresh-token family history."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from bson import ObjectId

from app.constants.roles import OWNER
from app.core.exceptions import ValidationError
from app.features.auth.models import User
from app.features.auth.session_lifecycle import IDLE_TIMEOUT
from app.features.daily_operations.service import DailyOperationsService
from app.utils.datetime import ensure_utc, ist_date_to_utc_midnight, utc_now


def union_seconds(intervals: list[tuple[datetime, datetime]]) -> int:
    """Count employee active time once, even with overlapping devices."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(
        (ensure_utc(start).astimezone(UTC), ensure_utc(end).astimezone(UTC))
        for start, end in intervals
    ):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return int(sum((end - start).total_seconds() for start, end in merged))


async def daily_sessions(
    service: DailyOperationsService,
    actor: User,
    *,
    page: int = 1,
    page_size: int = 20,
    employee: str = "",
    employee_name: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    await service.authorize(actor, "sessions")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Start date must be before end date.")
    query: dict[str, Any] = {}
    if actor.role != OWNER:
        query["user_id"] = actor.require_id()
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from.isoformat()
        if date_to:
            query["date"]["$lte"] = date_to.isoformat()
    pipeline: list[dict[str, Any]] = [
        {"$match": query},
        {
            "$lookup": {
                "from": "employees",
                "localField": "user_id",
                "foreignField": "user_id",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
        {"$match": {"employee.is_deleted": False}},
    ]
    if employee:
        if not ObjectId.is_valid(employee):
            raise ValidationError("Employee must be a CRM ID.")
        pipeline.append({"$match": {"employee._id": ObjectId(employee)}})
    if employee_name:
        pipeline.append(
            {
                "$match": {
                    "employee.display_name": {"$regex": re.escape(employee_name), "$options": "i"}
                }
            }
        )
    pipeline.append(
        {
            "$facet": {
                "items": [
                    {"$sort": {"date": -1, "_id": 1}},
                    {"$skip": (page - 1) * page_size},
                    {"$limit": page_size},
                ],
                "total": [{"$count": "value"}],
            }
        }
    )
    result = (await service.db.attendance_days.aggregate(pipeline).to_list(1))[0]
    days = result["items"]
    if not days:
        return {"items": [], "total": result["total"][0]["value"] if result["total"] else 0}
    now = utc_now()
    # Fetch all families for this page in one bounded query, never one query per employee.
    bounds = []
    for day in days:
        start = ist_date_to_utc_midnight(date.fromisoformat(day["date"]))
        end = ist_date_to_utc_midnight(date.fromisoformat(day["date"]) + timedelta(days=1))
        bounds.append(
            {
                "user_id": day["user_id"],
                "login_at": {"$lt": end},
                "$or": [
                    {"logout_at": {"$gte": start}},
                    {"last_activity_at": {"$gte": start - IDLE_TIMEOUT}},
                ],
            }
        )
    corrected_families = (
        await service.db.session_corrections.find(
            {
                "user_id": {"$in": [day["user_id"] for day in days]},
                "login_at": {"$lt": max(bound["login_at"]["$lt"] for bound in bounds)},
                "logout_at": {
                    "$gte": min(bound["$or"][0]["logout_at"]["$gte"] for bound in bounds)
                },
            },
            {"_id": 1},
        )
        .limit(10001)
        .to_list(10001)
    )
    if len(corrected_families) > 10000:
        raise ValidationError("Narrow the attendance filters to review corrected sessions.")
    if corrected_families:
        bounds.append(
            {
                "family_id": {"$in": [f["_id"] for f in corrected_families]},
                "user_id": {"$in": [day["user_id"] for day in days]},
            }
        )
    families = await service.db.sessions.aggregate(
        [
            {"$match": {"is_deleted": False, "$or": bounds}},
            {"$sort": {"updated_at": 1, "_id": 1}},
            {
                "$group": {
                    "_id": "$family_id",
                    "user_id": {"$first": "$user_id"},
                    "login_at": {"$min": "$login_at"},
                    "logout_at": {"$max": "$logout_at"},
                    "last_activity_at": {"$max": "$last_activity_at"},
                    "status": {"$last": "$status"},
                    "end_reason": {"$max": "$end_reason"},
                    "has_ended": {
                        "$max": {"$cond": [{"$in": ["$status", ["revoked", "logged_out"]]}, 1, 0]}
                    },
                }
            },
            {
                "$lookup": {
                    "from": "daily_session_visibility",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "visibility",
                }
            },
            {"$match": {"visibility.is_deleted": {"$ne": True}}},
            {"$limit": 10001},
        ]
    ).to_list(10001)
    if len(families) > 10000:
        raise ValidationError(
            "Narrow the attendance date/employee filters to review session history."
        )
    corrections = {
        c["_id"]: c
        for c in await service.db.session_corrections.find(
            {"_id": {"$in": [f["_id"] for f in families]}}
        ).to_list(10000)
    }
    items = []
    for day in days:
        start = ist_date_to_utc_midnight(date.fromisoformat(day["date"]))
        end = ist_date_to_utc_midnight(date.fromisoformat(day["date"]) + timedelta(days=1))
        history = []
        intervals = []
        for family in families:
            if family["user_id"] != day["user_id"]:
                continue
            correction = corrections.get(family["_id"], {})
            login = ensure_utc(correction.get("login_at", family["login_at"]))
            deadline = (
                ensure_utc(family.get("last_activity_at") or family["login_at"]) + IDLE_TIMEOUT
            )
            active = (
                family["status"] == "active"
                and not family["has_ended"]
                and deadline > now
                and not correction
            )
            logout = correction.get("logout_at", family.get("logout_at"))
            finish = ensure_utc(logout) if logout else min(now, deadline)
            if (
                family.get("end_reason") in {"session_revoked", "administrative_revocation"}
                and not correction
            ):
                finish = min(finish, deadline)
                logout = finish
            if not active and not logout and family["status"] == "active":
                logout = deadline
            if finish <= start or login >= end:
                continue
            intervals.append((max(login, start), min(finish, end)))
            history.append(
                {
                    "id": family["_id"],
                    "login_at": login,
                    "logout_at": logout,
                    "recorded_seconds": max(
                        0, int((min(finish, end) - max(login, start)).total_seconds())
                    ),
                    "status": "active" if active else "logged_out",
                    "end_reason": "administrative_correction"
                    if correction
                    else family.get("end_reason")
                    or (
                        None
                        if active
                        else "inactivity_timeout"
                        if family["status"] == "active"
                        else "legacy_unspecified"
                    ),
                    "correction_version": correction.get("version", 0),
                    "original_login_at": family["login_at"],
                    "original_logout_at": family.get("logout_at"),
                }
            )
        if not history:
            items.append(
                {
                    "id": day["_id"],
                    "date": day["date"],
                    "employee_id": str(day["employee"]["_id"]),
                    "employee_name": day["employee"]["display_name"],
                    "login_at": None,
                    "logout_at": None,
                    "recorded_seconds": 0,
                    "status": "no_visible_sessions",
                    "sessions": [],
                    "as_of": now,
                }
            )
            continue
        items.append(
            {
                "id": day["_id"],
                "date": day["date"],
                "employee_id": str(day["employee"]["_id"]),
                "employee_name": day["employee"]["display_name"],
                "login_at": min(h["login_at"] for h in history),
                "logout_at": max(
                    (
                        h["logout_at"]
                        for h in history
                        if h["logout_at"] and start <= ensure_utc(h["logout_at"]) < end
                    ),
                    default=None,
                ),
                "status": "active"
                if start <= now < end and any(h["status"] == "active" for h in history)
                else "logged_out",
                "recorded_seconds": union_seconds(intervals),
                "sessions": history,
                "as_of": now,
            }
        )
    return {"items": items, "total": result["total"][0]["value"] if result["total"] else 0}
