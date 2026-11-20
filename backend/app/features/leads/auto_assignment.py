"""Opt-in assignment within the existing company database, safe on standalone Mongo."""

import hashlib
import logging
from datetime import timedelta
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


class AssignmentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    employee_ids: list[str] = Field(default_factory=list, max_length=100)
    version: int = Field(default=0, ge=0)


def owner_only(actor: User) -> None:
    if actor.role != OWNER:
        raise ForbiddenError("Only an Owner can manage automatic assignment.")


class AutoAssignment:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def settings(self) -> dict[str, Any]:
        row = await self.db.auto_assignment_settings.find_one({"_id": "default"})
        return {
            k: (row or {}).get(k, default)
            for k, default in (
                ("enabled", False),
                ("employee_ids", []),
                ("version", 0),
                ("sequence", 0),
            )
        }

    async def save(self, payload: AssignmentSettings, actor: User) -> dict[str, Any]:
        owner_only(actor)
        if len(set(payload.employee_ids)) != len(payload.employee_ids):
            raise ValidationError("Choose each employee once.")
        previous_ids = (await self.settings())["employee_ids"]
        for employee_id in payload.employee_ids:
            if not ObjectId.is_valid(employee_id) or (
                employee_id not in previous_ids and not await self.active(employee_id)
            ):
                raise ValidationError("Choose active employees with active login accounts.")
        if payload.enabled and not payload.employee_ids:
            raise ValidationError("Select at least one employee before enabling assignment.")
        await self.db.auto_assignment_settings.update_one(
            {"_id": "default"}, {"$setOnInsert": {"version": 0, "sequence": 0}}, upsert=True
        )
        row = await self.db.auto_assignment_settings.find_one_and_update(
            {"_id": "default", "version": payload.version},
            {
                "$set": {
                    "enabled": payload.enabled,
                    "employee_ids": payload.employee_ids,
                    "updated_by": actor.require_id(),
                    "updated_at": utc_now(),
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not row:
            raise ConflictError("Assignment settings changed. Reload before saving.")
        await write_audit_log(
            self.db,
            event_type="auto_assignment_settings_updated",
            user_id=actor.require_id(),
            metadata={"enabled": payload.enabled, "employee_ids": payload.employee_ids},
        )
        return await self.settings()

    async def active(self, employee_id: str) -> bool:
        return employee_id in await self.active_pool([employee_id])

    async def active_pool(self, ids: list[str]) -> list[str]:
        employees = await self.db.employees.find(
            {
                "_id": {"$in": [ObjectId(eid) for eid in ids if ObjectId.is_valid(eid)]},
                "is_deleted": False,
                "status": "active",
            },
            {"user_id": 1},
        ).to_list(len(ids) or 1)
        users = {
            str(user["_id"])
            async for user in self.db.users.find(
                {
                    "_id": {"$in": [ObjectId(e["user_id"]) for e in employees]},
                    "is_deleted": False,
                    "status": "active",
                },
                {"_id": 1},
            )
        }
        available = {str(e["_id"]) for e in employees if e["user_id"] in users}
        return [eid for eid in ids if eid in available]

    async def notify(
        self, key: str, recipient: str, entity: str, record_id: str, failed: bool = False
    ) -> None:
        from app.features.reminders.constants import CATEGORY_BY_NOTIFICATION_TYPE, NotificationType
        from app.features.reminders.models import Notification

        kind = NotificationType.ASSIGNMENT_ATTENTION if failed else NotificationType.LEAD_ASSIGNED
        inactive = entity == "employee"
        notification = Notification(
            recipient_user_id=recipient,
            notification_type=kind,
            category=CATEGORY_BY_NOTIFICATION_TYPE[kind],
            title="Inactive employee holds assigned work"
            if inactive
            else "Assignment needs attention"
            if failed
            else "New work assigned",
            message="Review the linked employee and reassign work explicitly where needed. Historical ownership has been retained."
            if inactive
            else "A CRM record is awaiting assignment. Open Auto Assignment Settings to retry."
            if failed
            else "Open the linked CRM record to review your assigned work.",
            entity_type=entity,
            entity_id=record_id,
        )
        oid = ObjectId(hashlib.sha256(f"{key}:{recipient}".encode()).hexdigest()[:24])
        await self.db.notifications.update_one(
            {"_id": oid}, {"$setOnInsert": notification.model_dump(exclude={"id"})}, upsert=True
        )

    async def assign(self, collection: str, record_id: str, actor: User) -> None:
        """Claim -> reserve rotation -> persist assignment. Never raises to entry intake.

        Each reservation increments one singleton atomically; a crash can skip a slot,
        but cannot reuse it. Record lease tokens fence delayed writers after recovery.
        Business record is inserted FIRST, so failures cannot lose intake.
        """
        if collection not in {"leads", "applications"}:
            raise ValueError("Unsupported assignment collection")
        records = self.db[collection]
        token = str(ObjectId())
        now = utc_now()
        claimed = False
        try:
            settings = await self.settings()
            if not settings["enabled"]:
                if await records.find_one(
                    {
                        "_id": ObjectId(record_id),
                        "assigned_to": None,
                        "is_deleted": False,
                        "auto_assignment_eligible": True,
                    },
                    {"_id": 1},
                ):
                    async for owner in self.db.users.find(
                        {"role": OWNER, "status": "active", "is_deleted": False}, {"_id": 1}
                    ):
                        await self.notify(
                            f"unassigned:{collection}:{record_id}",
                            str(owner["_id"]),
                            "lead" if collection == "leads" else "application",
                            record_id,
                            True,
                        )
                return
            row = await records.find_one_and_update(
                {
                    "_id": ObjectId(record_id),
                    "is_deleted": False,
                    "assigned_to": None,
                    "auto_assignment_eligible": True,
                    "$or": [
                        {"assignment_lease_until": {"$exists": False}},
                        {"assignment_lease_until": {"$lte": now}},
                    ],
                },
                {
                    "$set": {
                        "assignment_token": token,
                        "assignment_lease_until": now + timedelta(minutes=2),
                        "assignment_pending": True,
                    },
                    "$inc": {"assignment_attempts": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if not row:
                return
            claimed = True
            # Reuse a durable reservation on retry unless the employee lost eligibility.
            selected = row.get("assignment_reserved_employee")
            sequence = row.get("assignment_sequence")
            from app.features.leads.constants import PRODUCT_CATEGORY_MODULE
            from app.features.leads.service import LeadService

            eligible = await LeadService(self.db)._employees_with_module_access(
                PRODUCT_CATEGORY_MODULE[row["product_category"]]
            )
            if (
                selected not in eligible
                or selected not in settings["employee_ids"]
                or not selected
                or not await self.active(selected)
            ):
                reservation = await self.db.auto_assignment_settings.find_one_and_update(
                    {"_id": "default", "enabled": True},
                    {"$inc": {"sequence": 1}},
                    return_document=ReturnDocument.AFTER,
                )
                if not reservation:
                    raise ValidationError("Automatic assignment is paused.")
                pool = await self.active_pool(
                    [eid for eid in reservation["employee_ids"] if eid in eligible]
                )
                if not pool:
                    raise ValidationError("No eligible employee is available.")
                sequence = reservation["sequence"]
                selected = pool[(sequence - 1) % len(pool)]
                await records.update_one(
                    {"_id": row["_id"], "assignment_token": token, "assigned_to": None},
                    {
                        "$set": {
                            "assignment_sequence": sequence,
                            "assignment_reserved_employee": selected,
                        }
                    },
                )
            result = await records.update_one(
                {
                    "_id": row["_id"],
                    "assignment_token": token,
                    "assigned_to": None,
                    "is_deleted": False,
                },
                {
                    "$set": {
                        "assigned_to": selected,
                        "assigned_by": actor.require_id(),
                        "assigned_at": now,
                        "assignment_pending": False,
                        "assignment_error": None,
                        "assignment_origin": "automatic",
                        "assignment_event_pending": {
                            "employee_id": selected,
                            "sequence": sequence,
                            "actor_id": actor.require_id(),
                            "at": now,
                        },
                        "auto_assignment_eligible": False,
                        "updated_at": now,
                    },
                    "$unset": {"assignment_lease_until": ""},
                    "$inc": {"version": 1},
                },
            )
            if result.modified_count:
                await self.deliver_event(collection, record_id)
        except Exception:  # noqa: BLE001 -- intake must survive assignment/notification failures
            # Fixed error code: database/validation exceptions can include personal data.
            try:
                result = await records.update_one(
                    {"_id": ObjectId(record_id), "assignment_token": token, "assigned_to": None},
                    {
                        "$set": {
                            "assignment_error": "assignment_unavailable",
                            "assignment_pending": True,
                        },
                        "$unset": {"assignment_lease_until": ""},
                    },
                )
                if claimed and result.modified_count:
                    async for owner in self.db.users.find(
                        {"role": OWNER, "status": "active", "is_deleted": False}, {"_id": 1}
                    ):
                        await self.notify(
                            f"failed:{collection}:{record_id}",
                            str(owner["_id"]),
                            "lead" if collection == "leads" else "application",
                            record_id,
                            True,
                        )
            except PyMongoError:
                logging.getLogger(__name__).warning(
                    "Assignment recovery deferred; original CRM record retained."
                )

    async def deliver_event(self, collection: str, record_id: str) -> None:
        row = await self.db[collection].find_one(
            {"_id": ObjectId(record_id), "assignment_event_pending": {"$type": "object"}}
        )
        if not row:
            return
        event = row["assignment_event_pending"]
        key = f"assigned:{collection}:{record_id}:{event['sequence']}"
        from app.shared.audit_log import AuditLog

        audit = AuditLog(
            event_type="crm_auto_assigned",
            user_id=event["actor_id"],
            created_at=event["at"],
            metadata={
                "collection": collection,
                "record_id": record_id,
                "old_employee_id": None,
                "employee_id": event["employee_id"],
                "sequence": event["sequence"],
            },
        )
        await self.db.audit_logs.update_one(
            {"_id": ObjectId(hashlib.sha256(key.encode()).hexdigest()[:24])},
            {"$setOnInsert": audit.model_dump(exclude={"id"})},
            upsert=True,
        )
        if collection == "leads":
            from app.features.leads.models import LeadActivity

            activity = LeadActivity(
                lead_id=record_id,
                event_type="assigned",
                created_by=event["actor_id"],
                created_at=event["at"],
                metadata={
                    "employee_id": event["employee_id"],
                    "source": "automatic",
                    "sequence": event["sequence"],
                },
            )
            await self.db.lead_activities.update_one(
                {"_id": ObjectId(hashlib.sha256(key.encode()).hexdigest()[:24])},
                {"$setOnInsert": activity.model_dump(exclude={"id"})},
                upsert=True,
            )
        employee = await self.db.employees.find_one(
            {"_id": ObjectId(event["employee_id"])}, {"user_id": 1}
        )
        if (
            employee
            and row.get("assigned_to") == event["employee_id"]
            and not row.get("is_deleted")
        ):
            await self.notify(
                key,
                employee["user_id"],
                "lead" if collection == "leads" else "application",
                record_id,
            )
        await self.db[collection].update_one(
            {"_id": row["_id"], "assignment_event_pending": event},
            {"$unset": {"assignment_event_pending": ""}},
        )

    async def recover(self) -> dict[str, int]:
        counts = {"retried": 0, "events": 0}
        owner = await self.db.users.find_one(
            {"role": OWNER, "status": "active", "is_deleted": False}
        )
        for collection in ("leads", "applications"):
            async for row in (
                self.db[collection]
                .find({"assignment_event_pending": {"$type": "object"}}, {"_id": 1})
                .limit(100)
            ):
                await self.deliver_event(collection, str(row["_id"]))
                counts["events"] += 1
            if owner and (await self.settings())["enabled"]:
                async for row in (
                    self.db[collection]
                    .find(
                        {
                            "is_deleted": False,
                            "assigned_to": None,
                            "auto_assignment_eligible": True,
                            "assignment_pending": True,
                            "$or": [
                                {"assignment_attempts": {"$exists": False}},
                                {"assignment_attempts": {"$lt": 3}},
                            ],
                        },
                        {"_id": 1},
                    )
                    .limit(100)
                ):
                    await self.assign(collection, str(row["_id"]), User.model_validate(owner))
                    counts["retried"] += 1
        # Historical ownership is preserved when an employee is deactivated.
        checkpoint = await self.db.auto_assignment_scan_state.find_one({"_id": "inactive"})
        query: dict[str, Any] = {"status": {"$ne": "active"}}
        if checkpoint and checkpoint.get("last_id"):
            query["_id"] = {"$gt": checkpoint["last_id"]}
        employees = (
            await self.db.employees.find(query, {"_id": 1, "updated_at": 1})
            .sort("_id", 1)
            .limit(100)
            .to_list(100)
        )
        for employee in employees:
            eid = str(employee["_id"])
            if owner and (
                await self.db.leads.count_documents({"assigned_to": eid, "is_deleted": False})
                or await self.db.applications.count_documents(
                    {"assigned_to": eid, "is_deleted": False}
                )
            ):
                await self.notify(
                    f"inactive-work:{eid}:{employee.get('updated_at')}",
                    str(owner["_id"]),
                    "employee",
                    eid,
                    True,
                )
        await self.db.auto_assignment_scan_state.update_one(
            {"_id": "inactive"},
            {"$set": {"last_id": employees[-1]["_id"] if employees else None}},
            upsert=True,
        )
        return counts


async def ensure_assignment_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.audit_logs.create_index([("event_type", 1), ("created_at", -1)])
    for name in ("leads", "applications"):
        await db[name].create_index([("assignment_pending", 1), ("assigned_to", 1)])
        await db[name].create_index(
            [("auto_assignment_eligible", 1), ("assigned_to", 1), ("created_at", 1)]
        )
        await db[name].create_index("assignment_event_pending.sequence", sparse=True)
        await db[name].create_index([("is_deleted", 1), ("created_at", 1), ("assigned_to", 1)])
        await db[name].create_index(
            "assignment_sequence",
            unique=True,
            partialFilterExpression={"assignment_sequence": {"$type": "number"}},
        )
