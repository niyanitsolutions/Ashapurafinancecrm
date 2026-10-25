"""Bounded, idempotent internal inbox delivery. Never sends external messages."""

import hashlib
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.daily_operations.service import OPEN_STATUSES
from app.features.reminders.constants import CATEGORY_BY_NOTIFICATION_TYPE, NotificationType
from app.features.reminders.models import Notification
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ist_date_to_utc_midnight, to_ist, utc_now


async def deliver_notifications(db: AsyncIOMotorDatabase[Any]) -> dict[str, int]:
    counts = {"created": 0, "skipped": 0}
    today = ist_date_to_utc_midnight(to_ist(utc_now()).date())
    for kind, collection in (
        ("follow-ups", db.daily_follow_ups),
        ("issues", db.operational_issues),
    ):
        checkpoint = await db.daily_notification_cursors.find_one({"_id": kind})
        query: dict[str, Any] = {"is_deleted": False}
        if checkpoint and checkpoint.get("last_id"):
            query["_id"] = {"$gt": checkpoint["last_id"]}
        if kind == "follow-ups":
            query.update(status={"$in": OPEN_STATUSES}, due_date={"$ne": None, "$lte": today})
        else:
            query.update(
                assignment_notification_pending={"$ne": None},
                assigned_to={"$ne": None},
                status={"$ne": "RESOLVED"},
            )
        documents = (
            await collection.find(
                query,
                {
                    "assigned_to": 1,
                    "lead_oid": 1,
                    "due_date": 1,
                    "notified_due_date": 1,
                    "notified_employee": 1,
                    "assignment_notification_pending": 1,
                    "version": 1,
                },
            )
            .sort("_id", 1)
            .limit(100)
            .to_list(100)
        )
        for doc in documents:
            employee_id = doc.get("assigned_to")
            if kind == "follow-ups":
                lead = await db.leads.find_one(
                    {"_id": doc["lead_oid"], "is_deleted": False}, {"assigned_to": 1}
                )
                employee_id = lead.get("assigned_to") if lead else None
                if (
                    doc.get("notified_due_date") == doc["due_date"]
                    and doc.get("notified_employee") == employee_id
                ):
                    continue
            employee = (
                await db.employees.find_one(
                    {"_id": ObjectId(employee_id), "is_deleted": False, "status": "active"}
                )
                if ObjectId.is_valid(employee_id)
                else None
            )
            user_id = employee["user_id"] if employee else employee_id
            user = (
                await db.users.find_one(
                    {"_id": ObjectId(user_id), "status": "active", "is_deleted": False}
                )
                if ObjectId.is_valid(user_id)
                else None
            )
            actor = User.model_validate(user) if user else None
            engine = PermissionEngine(db)
            allowed = actor is not None and await engine.has_permission(
                actor, module="daily_operations", resource=kind, action="view"
            )
            if allowed and actor is not None and kind == "follow-ups":
                allowed = await engine.has_permission(
                    actor, module="leads", resource="leads", action="view"
                )
            if not allowed:
                counts["skipped"] += 1
                continue
            assert actor is not None
            token = (
                str(doc["due_date"]) + str(employee_id)
                if kind == "follow-ups"
                else doc["assignment_notification_pending"]
            )
            key = hashlib.sha256(f"{kind}:{doc['_id']}:{token}".encode()).hexdigest()
            notification_type = (
                NotificationType.DAILY_FOLLOW_UP_DUE
                if kind == "follow-ups"
                else NotificationType.OPERATIONAL_ISSUE_ASSIGNED
            )
            notification = Notification(
                recipient_user_id=actor.require_id(),
                notification_type=notification_type,
                category=CATEGORY_BY_NOTIFICATION_TYPE[notification_type],
                title="Daily follow-up due"
                if kind == "follow-ups"
                else "Operational issue assigned",
                message="Open Daily Operations to review your authorized records.",
                entity_type="daily_follow_up" if kind == "follow-ups" else "operational_issue",
                entity_id=str(doc["_id"]),
            )
            result = await db.notifications.update_one(
                {"_id": ObjectId(key[:24])},
                {"$setOnInsert": notification.model_dump(exclude={"id"})},
                upsert=True,
            )
            if result.upserted_id:
                counts["created"] += 1
                await write_audit_log(
                    db,
                    event_type="daily_internal_notification",
                    user_id=actor.require_id(),
                    metadata={"kind": kind, "record_id": str(doc["_id"])},
                )
            if kind == "follow-ups":
                await collection.update_one(
                    {"_id": doc["_id"], "version": doc["version"]},
                    {
                        "$set": {
                            "notified_due_date": doc["due_date"],
                            "notified_employee": employee_id,
                        }
                    },
                )
            else:
                await collection.update_one(
                    {"_id": doc["_id"], "assignment_notification_pending": token},
                    {"$set": {"assignment_notification_pending": None}},
                )
        await db.daily_notification_cursors.update_one(
            {"_id": kind},
            {
                "$set": {
                    "last_id": documents[-1]["_id"] if len(documents) == 100 else None,
                    "updated_at": utc_now(),
                    "last_result": counts,
                }
            },
            upsert=True,
        )
    return counts
