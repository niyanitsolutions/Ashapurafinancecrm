"""Attendance-only reconciliation retaining source history and correction values."""

from datetime import date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.auth.indexes import ensure_attendance_indexes
from app.features.auth.session_lifecycle import ensure_summary
from app.features.daily_operations.attendance import session_window, union_seconds
from app.features.daily_operations.calendar import day_segments
from app.utils.datetime import ensure_utc, to_ist, utc_now


async def reconcile_attendance(
    db: AsyncIOMotorDatabase[Any],
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utc_now()
    names = ("attendance_days", "sessions", "session_corrections")
    before = {name: await db[name].count_documents({}) for name in names}
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry_run",
        "as_of": now.isoformat(),
        "before": before,
        "issues": [],
        "findings": [],
        "issue_count": 0,
        "cross_midnight_families": 0,
        "carry_in_days": 0,
        "stale_active_families": 0,
        "missing_logout_families": 0,
        "duplicate_token_events": 0,
        "wrong_stored_login_dates": 0,
        "wrong_stored_durations": 0,
        "unattributed_summaries": 0,
    }

    def issue(kind: str, record_id: Any) -> None:
        report["issue_count"] += 1
        if len(report["issues"]) < 200:
            report["issues"].append({"kind": kind, "id": str(record_id)})

    def finding(kind: str, record_id: Any) -> None:
        if len(report["findings"]) < 200:
            report["findings"].append({"kind": kind, "id": str(record_id)})

    users = {str(u["_id"]) async for u in db.users.find({}, {"_id": 1})}
    async for group in db.employees.aggregate(
        [
            {"$match": {"is_deleted": False}},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        ]
    ):
        if group["_id"] not in users or group["count"] != 1:
            issue("inconsistent_employee_identity", group["_id"])
    async for group in db.sessions.aggregate(
        [
            {"$match": {"token_id": {"$type": "string"}}},
            {"$group": {"_id": "$token_id", "count": {"$sum": 1}, "id": {"$first": "$_id"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
    ):
        report["duplicate_token_events"] += group["count"] - 1
        issue("duplicate_session_token", group["id"])  # Never expose the token ID.
    corrections = {c["_id"]: c async for c in db.session_corrections.find({})}
    hidden = {
        doc["_id"]
        async for doc in db.daily_session_visibility.find({"is_deleted": True}, {"_id": 1})
    }
    bindings: dict[str, tuple[str, dict[str, Any]]] = {}
    expected: dict[str, dict[str, Any]] = {}
    families_seen = set()
    async for family in db.sessions.aggregate(
        [
            {"$match": {"is_deleted": False}},
            {"$sort": {"updated_at": 1, "_id": 1}},
            {
                "$group": {
                    "_id": "$family_id",
                    "user_id": {"$first": "$user_id"},
                    "user_values": {"$addToSet": "$user_id"},
                    "login_values": {"$addToSet": "$login_at"},
                    "login_at": {"$min": "$login_at"},
                    "logout_at": {"$max": "$logout_at"},
                    "last_activity_at": {"$max": "$last_activity_at"},
                    "status": {"$last": "$status"},
                    "end_reason": {"$max": "$end_reason"},
                    "has_ended": {
                        "$max": {"$cond": [{"$in": ["$status", ["logged_out", "revoked"]]}, 1, 0]}
                    },
                }
            },
        ]
    ):
        family_id, user_id = family["_id"], family.get("user_id")
        families_seen.add(family_id)
        correction = corrections.get(family_id, {})
        if (
            not isinstance(family_id, str)
            or not family_id
            or user_id not in users
            or len(family["user_values"]) != 1
            or len(family["login_values"]) != 1
            or not isinstance(family.get("login_at"), datetime)
            or not isinstance(family.get("last_activity_at"), datetime)
            or (
                family.get("logout_at") is not None
                and not isinstance(family["logout_at"], datetime)
            )
            or (correction.get("user_id") and correction["user_id"] != user_id)
        ):
            issue("ambiguous_family_identity_or_timestamps", family_id)
            continue
        if (
            ensure_utc(family["login_at"]) > now
            or ensure_utc(family["last_activity_at"]) > now
            or ensure_utc(family["last_activity_at"]) < ensure_utc(family["login_at"])
        ):
            issue("invalid_source_activity_order", family_id)
            continue
        if not family.get("logout_at"):
            report["missing_logout_families"] += 1
            if family["status"] != "active" and not correction:
                issue("ended_family_missing_logout", family_id)
                continue
        if correction and (
            not isinstance(correction.get("login_at"), datetime)
            or not isinstance(correction.get("logout_at"), datetime)
        ):
            issue("invalid_manual_correction", family_id)
            continue
        if correction and not correction.get("user_id"):
            bindings[family_id] = (user_id, correction)
        login, finish, _, active = session_window(family, correction, now)
        if (
            finish < login
            or login > now
            or finish > now
            or (to_ist(finish).date() - to_ist(login).date()).days > 3660
        ):
            issue("invalid_or_excessive_source_interval", family_id)
            continue
        if family["status"] == "active" and not active and not correction:
            report["stale_active_families"] += 1
        if family_id in hidden:
            continue
        segments = list(day_segments(login, finish))
        if len(segments) > 1:
            report["cross_midnight_families"] += 1
            report["carry_in_days"] += len(segments) - 1
        # A just-issued login with no elapsed time still owns its login-day key.
        if not segments:
            segments = [(to_ist(login).date(), login, login)]
        for day, start, end in segments:
            key = f"{user_id}:{day.isoformat()}"
            expected.setdefault(key, {"user_id": user_id, "start": start, "intervals": []})
            expected[key]["intervals"].append((start, end))
    for family_id in corrections.keys() - families_seen:
        issue("orphan_manual_correction", family_id)
    existing = set()
    pairs = set()
    async for summary in db.attendance_days.find({}):
        key = str(summary["_id"])
        existing.add(key)
        try:
            day = date.fromisoformat(summary["date"])
            pair = (summary["user_id"], day.isoformat())
        except (KeyError, ValueError, TypeError):
            issue("invalid_summary_identity_or_date", key)
            continue
        if pair in pairs:
            issue("duplicate_employee_date_summary", key)
        pairs.add(pair)
        if pair[0] not in users or key != f"{pair[0]}:{pair[1]}":
            issue("noncanonical_summary_identity", key)
        stored_login = summary.get("login_at")
        if isinstance(stored_login, datetime) and to_ist(stored_login).date() != day:
            report["wrong_stored_login_dates"] += 1
            finding("stale_stored_login_date_ignored_by_projection", key)
        if key not in expected:
            report["unattributed_summaries"] += 1
            finding("summary_without_attributable_source", key)
        elif "recorded_seconds" in summary and summary["recorded_seconds"] != union_seconds(
            expected[key]["intervals"]
        ):
            report["wrong_stored_durations"] += 1
            finding("stale_stored_duration_ignored_by_projection", key)
    missing = expected.keys() - existing
    report.update(
        expected_source_days=len(expected),
        planned_correction_bindings=len(bindings),
        correction_bindings_created=0,
        planned_inserts=len(missing),
        created=0,
        projected_summary_count=before["attendance_days"] + len(missing),
    )
    report["status"] = "BLOCKED" if report["issue_count"] else "PASS"
    if apply and not report["issue_count"]:
        await ensure_attendance_indexes(db)
        for family_id, (user_id, original) in bindings.items():
            result = await db.session_corrections.update_one(
                {
                    "_id": family_id,
                    "user_id": None,
                    "version": original.get("version"),
                    "login_at": original["login_at"],
                    "logout_at": original["logout_at"],
                },
                {
                    "$set": {"user_id": user_id},
                    "$push": {
                        "reconciliation_history": {
                            "source": "calendar_reconciliation",
                            "at": utc_now(),
                            "before": {"user_id": None},
                            "after": {"user_id": user_id},
                        }
                    },
                },
            )
            report["correction_bindings_created"] += result.modified_count
            if not result.modified_count:
                current = await db.session_corrections.find_one({"_id": family_id})
                if (
                    not current
                    or current.get("user_id") != user_id
                    or current.get("version") != original.get("version")
                ):
                    issue("correction_changed_during_reconciliation", family_id)
                    report["status"] = "BLOCKED"
        if report["status"] == "BLOCKED":
            report["after"] = {name: await db[name].count_documents({}) for name in names}
            return report
        for key in sorted(missing):
            source = expected[key]
            await ensure_summary(db, source["user_id"], source["start"])
        report["created"] = await db.attendance_days.count_documents({}) - before["attendance_days"]
    report["after"] = {name: await db[name].count_documents({}) for name in names}
    return report
