"""HR audit events deliver idempotent messages through the existing internal inbox."""

import hashlib
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.features.reminders.constants import NotificationCategory, NotificationType
from app.features.reminders.models import Notification
from app.shared.audit_log import write_audit_log

OWNER_EVENTS = {
    "employee_onboarding_submitted",
    "employee_document_version_uploaded",
    "employee_edit_requested",
    "employee_leave_applied",
}
EMPLOYEE_EVENTS = {
    "employee_onboarding_approve",
    "employee_onboarding_changes_required",
    "employee_document_approved",
    "employee_document_rejected",
    "employee_document_reupload_required",
    "employee_edit_approved",
    "employee_edit_rejected",
    "employee_leave_approved",
    "employee_leave_rejected",
    "employee_leave_cancelled",
}


async def deliver(db: Any, event: dict[str, Any]) -> int:
    payload = event.get("metadata", {}).get("hr_notification")
    if not payload:
        return 0
    count = 0
    for recipient in payload["recipients"]:
        oid = ObjectId(hashlib.sha256((payload["key"] + ":" + recipient).encode()).hexdigest()[:24])
        notification = Notification(
            recipient_user_id=recipient,
            notification_type=NotificationType.EMPLOYEE_HR,
            category=NotificationCategory.SYSTEM,
            title=payload["title"],
            message=payload["message"],
            entity_type=payload["entity_type"],
            entity_id=payload["employee_id"],
        )
        result = await db.notifications.update_one(
            {"_id": oid}, {"$setOnInsert": notification.model_dump(exclude={"id"})}, upsert=True
        )
        count += int(result.upserted_id is not None)
    return count


def queue_event(
    mutation: dict[str, Any], event_type: str, user_id: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Append the event atomically with the employee state/history mutation."""
    event_id = str(ObjectId())
    meta = dict(metadata)
    for path, value in mutation.get("$push", {}).items():
        if path.endswith(".history") and isinstance(value, dict) and "reason" in value:
            meta["reason"] = value["reason"]
    if "onboarding.reason" in mutation.get("$set", {}):
        meta["reason"] = mutation["$set"]["onboarding.reason"]
    for field in ("hr_edit_requests", "hr_leave_requests"):
        rows = mutation.get("$set", {}).get(field, [])
        target: dict[str, Any] = next((row for row in rows if row["id"] == meta.get("request_id")), {})
        if target:
            meta["reason"] = target.get(
                "review_reason", target.get("reason", "") if field == "hr_edit_requests" else ""
            )
    meta["hr_event_id"] = event_id
    event = {"id": event_id, "event_type": event_type, "user_id": user_id, "metadata": meta}
    return mutation | {"$push": mutation.get("$push", {}) | {"hr_event_outbox": event}}


async def record_event(
    db: Any,
    *,
    event_type: str,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    metadata = dict(metadata or {})
    employee_id = metadata.get("employee_id")
    employee = None
    queued = None
    if employee_id and ObjectId.is_valid(employee_id):
        employee = await db.employees.find_one({"_id": ObjectId(employee_id), "is_deleted": False})
        if employee:
            queued = next(
                (
                    event
                    for event in employee.get("hr_event_outbox", [])
                    if event["event_type"] == event_type
                    and all(event["metadata"].get(key) == value for key, value in metadata.items())
                ),
                None,
            )
            if queued:
                metadata = dict(queued["metadata"])
                user_id = queued["user_id"]
            elif event_type.startswith("employee_"):
                # A worker may have delivered the committed event before the API resumed.
                previous = await db.audit_logs.find_one(
                    {
                        "event_type": event_type,
                        **{"metadata." + key: value for key, value in metadata.items()},
                    }
                )
                if previous:
                    return
    if employee and event_type in OWNER_EVENTS | EMPLOYEE_EVENTS:
        recipients = (
            [
                str(row["_id"])
                async for row in db.users.find(
                    {"role": "owner", "status": "active", "is_deleted": False}, {"_id": 1}
                )
            ]
            if event_type in OWNER_EVENTS
            else [employee["user_id"]]
        )
        reason = metadata.get("reason", "")
        action = event_type.removeprefix("employee_").replace("_", " ")
        key = metadata.get("hr_event_id") or ":".join(
            str(item)
            for item in (
                event_type,
                employee_id,
                metadata.get("request_id", ""),
                metadata.get("category", ""),
                metadata.get("version", employee.get("onboarding", {}).get("version", 0)),
            )
        )
        metadata["hr_notification"] = {
            "key": key,
            "employee_id": employee_id,
            "recipients": recipients,
            "title": employee["employee_code"] + ": " + action,
            "message": action.capitalize()
            + (". " + reason if reason else ". Open the employee workflow to review details."),
            "entity_type": "employee_leave" if "leave_" in event_type else "employee_hr",
        }
        metadata["hr_notification_delivered"] = False
    try:
        await write_audit_log(
            db, event_type=event_type, user_id=user_id, metadata=metadata, **kwargs
        )
    except DuplicateKeyError:
        existing = await db.audit_logs.find_one(
            {"metadata.hr_event_id": metadata.get("hr_event_id")}
        )
        if not existing:
            raise
        metadata = existing["metadata"]
    await deliver(db, {"metadata": metadata})
    if "hr_notification" in metadata:
        await db.audit_logs.update_many(
            {"metadata.hr_notification.key": metadata["hr_notification"]["key"]},
            {"$set": {"metadata.hr_notification_delivered": True}},
        )
    if queued and employee:
        await db.employees.update_one(
            {"_id": employee["_id"]}, {"$pull": {"hr_event_outbox": {"id": queued["id"]}}}
        )


async def retry_delivery(db: Any) -> dict[str, int]:
    count = 0
    async for employee in db.employees.find(
        {"hr_event_outbox.0": {"$exists": True}, "is_deleted": False}
    ).limit(100):
        for event in employee.get("hr_event_outbox", []):
            # Complete a missing secondary document index without copying/deleting files.
            meta = event["metadata"]
            if event["event_type"] == "employee_document_version_uploaded":
                current = employee.get("hr_documents", {}).get(meta.get("category"), {})
                version = next(
                    (
                        row
                        for row in [current] + current.get("versions", [])
                        if row.get("version") == meta.get("version")
                    ),
                    None,
                )
                if version and version.get("files"):
                    file = version["files"][0]
                    await db.employee_documents.update_one(
                        {"_id": ObjectId(version["id"])},
                        {
                            "$setOnInsert": {
                                "employee_id": str(employee["_id"]),
                                "document_type": meta["category"],
                                "file_name": file["file_name"],
                                "s3_key": file["s3_key"],
                                "content_type": file["content_type"],
                                "files": version["files"],
                                "created_at": version["uploaded_at"],
                                "updated_at": version["uploaded_at"],
                                "created_by": version["uploaded_by"],
                                "is_deleted": False,
                                "status": version["status"],
                            }
                        },
                        upsert=True,
                    )
            await record_event(
                db, event_type=event["event_type"], user_id=event["user_id"], metadata=meta
            )
            count += 1
            if count >= 200:
                return {"created": count}
    query = {
        "metadata.hr_notification": {"$exists": True},
        "metadata.hr_notification_delivered": {"$ne": True},
    }
    async for event in db.audit_logs.find(query).sort("created_at", 1).limit(200):
        count += await deliver(db, event)
        await db.audit_logs.update_one(
            {"_id": event["_id"]}, {"$set": {"metadata.hr_notification_delivered": True}}
        )
    return {"created": count}
