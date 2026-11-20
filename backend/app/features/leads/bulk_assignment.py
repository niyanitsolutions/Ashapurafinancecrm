"""Bounded, previewed assignment of existing records. No business record creation."""

import hashlib
import json
from datetime import timedelta
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.exceptions import ConflictError, ForbiddenError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.leads.assignment_policy import eligible_employees, eligible_record, intake_filter
from app.features.leads.auto_assignment import AutoAssignment, owner_only
from app.utils.datetime import utc_now


class BulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=100)
    employee_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    allow_reassignment: bool = False
    preview_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[dict[str, str]] = Field(min_length=1, max_length=100)
    preview_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{24}$")


async def authorize(
    db: AsyncIOMotorDatabase[Any], actor: User, collection: str, row: dict[str, Any] | None = None
) -> None:
    if collection == "applications":
        owner_only(actor)  # Same boundary as individual Application assignment.
    elif not await PermissionEngine(db).has_permission(
        actor,
        module="leads",
        resource="leads",
        action="assign",
        branch_id=(row or {}).get("branch_id"),
        department_id=(row or {}).get("department_id"),
    ):
        raise ForbiddenError("Lead assignment permission is required.")


def fingerprint(
    records: list[dict[str, str]], employee: str | None, reassign: bool, mode: str
) -> str:
    return hashlib.sha256(
        json.dumps([records, employee, reassign, mode], sort_keys=True).encode()
    ).hexdigest()


async def resolve(
    db: AsyncIOMotorDatabase[Any], actor: User, collection: str, record_id: str
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(record_id):
        return None
    row = await db[collection].find_one({"_id": ObjectId(record_id), "is_deleted": False})
    if row:
        await authorize(db, actor, collection, row)
    return row


async def prepare(
    db: AsyncIOMotorDatabase[Any],
    actor: User,
    records: list[dict[str, str]],
    employee: str | None,
    reassign: bool,
    mode: str,
) -> dict[str, Any]:
    snapshots = []
    for item in records:
        collection, rid = item["collection"], item["id"]
        result: dict[str, Any] = {**item, "status": "eligible", "reason": "Ready for confirmation"}
        try:
            row = await resolve(db, actor, collection, rid)
            if row is None:
                result.update(status="failed", reason="Record unavailable or invalid ID")
            elif not await eligible_record(db, collection, row):
                result.update(status="skipped", reason="Record is outside eligible intake")
            elif row.get("assigned_to") == employee and employee:
                result.update(status="skipped", reason="Already assigned to this employee")
            elif row.get("assigned_to") and not reassign:
                result.update(status="skipped", reason="Existing assignment preserved")
            elif employee and not await eligible_employees(db, [employee], row, collection):
                result.update(status="failed", reason="Employee inactive or lacks required access")
            else:
                result.update(
                    version=row.get("version", 1), previous_employee=row.get("assigned_to")
                )
                # Capture exact ownership expectations for dependent copies, not inferred people.
                mirrors = []
                if collection == "applications":
                    case = await db.application_workflows.find_one(
                        {
                            "application_id": str(row["_id"]),
                            "case_type": "loan",
                            "is_deleted": False,
                        }
                    )
                    linked = (
                        await db.leads.find_one(
                            {"_id": ObjectId(row["lead_id"]), "is_deleted": False}
                        )
                        if ObjectId.is_valid(row.get("lead_id"))
                        else None
                    )
                    for target, document in (("application_workflows", case), ("leads", linked)):
                        if document:
                            if (
                                mode != "retry"
                                and document.get("assigned_to")
                                and not reassign
                                and document.get("assigned_to") != employee
                            ):
                                result.update(
                                    status="skipped",
                                    reason="Linked record has an existing owner; explicit reassignment required",
                                )
                            mirrors.append(
                                {
                                    "collection": target,
                                    "id": str(document["_id"]),
                                    "previous_employee": document.get("assigned_to"),
                                }
                            )
                result["mirrors"] = mirrors
        except ForbiddenError:
            result.update(status="failed", reason="Record unavailable or not permitted")
        snapshots.append(result)
    oid = ObjectId()
    await db.assignment_previews.insert_one(
        {
            "_id": oid,
            "actor_id": actor.require_id(),
            "fingerprint": fingerprint(records, employee, reassign, mode),
            "employee_id": employee,
            "allow_reassignment": reassign,
            "mode": mode,
            "records": snapshots,
            "expires_at": utc_now() + timedelta(minutes=10),
        }
    )
    return summary(snapshots, str(oid), preview=True)


def summary(
    results: list[dict[str, Any]], preview_id: str, *, preview: bool = False
) -> dict[str, Any]:
    public = [
        {k: r[k] for k in ("id", "collection", "status", "reason") if k in r} for r in results
    ]
    return {
        "preview_id": preview_id,
        "preview": preview,
        "total": len(results),
        "assigned": sum(r["status"] == "assigned" for r in results),
        "eligible": sum(r["status"] == "eligible" for r in results),
        "skipped": sum(r["status"] == "skipped" for r in results),
        "failed": sum(r["status"] == "failed" for r in results),
        "results": public,
    }


async def execute(
    db: AsyncIOMotorDatabase[Any],
    actor: User,
    records: list[dict[str, str]],
    employee: str | None,
    reassign: bool,
    mode: str,
    preview_id: str | None,
) -> dict[str, Any]:
    for item in records:
        await authorize(db, actor, item["collection"])
    if mode == "retry":
        owner_only(actor)
    if not preview_id:
        return await prepare(db, actor, records, employee, reassign, mode)
    preview = await db.assignment_previews.find_one(
        {
            "_id": ObjectId(preview_id),
            "actor_id": actor.require_id(),
            "fingerprint": fingerprint(records, employee, reassign, mode),
            "expires_at": {"$gt": utc_now()},
        }
    )
    if not preview:
        raise ConflictError("Preview expired or changed. Review the selection again.")
    service = AutoAssignment(db)
    results = []
    for snapshot in preview["records"]:
        result = dict(snapshot)
        if result["status"] != "eligible":
            results.append(result)
            continue
        collection, rid = result["collection"], result["id"]
        operation = f"bulk:{preview_id}:{rid}"
        receipt_id = ObjectId(
            hashlib.sha256(f"assigned:{collection}:{rid}:{operation}".encode()).hexdigest()[:24]
        )
        try:
            row = await resolve(db, actor, collection, rid)
            receipt = await db.audit_logs.find_one({"_id": receipt_id})
            if receipt:
                result.update(status="assigned", reason="Previously completed request")
            elif row and (row.get("assignment_event_pending") or {}).get("sequence") == operation:
                await service.deliver_event(collection, rid)
                result.update(status="assigned", reason="Assignment completed after recovery")
            elif not row or not await eligible_record(db, collection, row):
                result.update(status="skipped", reason="Record no longer eligible")
            elif (
                row.get("version", 1) != snapshot["version"]
                or row.get("assigned_to") != snapshot["previous_employee"]
            ):
                result.update(status="skipped", reason="Record changed since preview; review again")
            elif mode == "retry":
                if not (await service.settings())["enabled"]:
                    result.update(status="skipped", reason="Automatic assignment is paused")
                else:
                    await db[collection].update_one(
                        {"_id": row["_id"], "assigned_to": None, "version": snapshot["version"]},
                        {"$set": {"auto_assignment_eligible": True}},
                    )
                    await service.assign(collection, rid, actor, source="retry")
                    current = await db[collection].find_one({"_id": row["_id"]}, {"assigned_to": 1})
                    result.update(
                        status="assigned" if (current or {}).get("assigned_to") else "failed",
                        reason="Assigned"
                        if (current or {}).get("assigned_to")
                        else "No eligible assignee or assignment still processing",
                    )
            elif not employee or not await eligible_employees(db, [employee], row, collection):
                result.update(status="failed", reason="Employee inactive or lacks required access")
            else:
                await service.deliver_event(collection, rid)
                now = utc_now()
                changed = await db[collection].find_one_and_update(
                    {
                        "_id": row["_id"],
                        "is_deleted": False,
                        "version": snapshot["version"],
                        "assigned_to": snapshot["previous_employee"],
                        "assignment_event_pending": {"$exists": False},
                        **intake_filter(collection),
                    },
                    {
                        "$set": {
                            "assigned_to": employee,
                            "assigned_by": actor.require_id(),
                            "assigned_at": now,
                            "assignment_origin": "bulk",
                            "assignment_token": None,
                            "assignment_pending": False,
                            "auto_assignment_eligible": False,
                            "assignment_event_pending": {
                                "employee_id": employee,
                                "old_employee_id": snapshot["previous_employee"],
                                "sequence": operation,
                                "source": "bulk",
                                "actor_id": actor.require_id(),
                                "at": now,
                                "mirrors": snapshot.get("mirrors", []),
                            },
                        },
                        "$inc": {"version": 1},
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if changed:
                    await service.deliver_event(collection, rid)
                    result.update(status="assigned", reason="Assigned")
                else:
                    result.update(
                        status="skipped",
                        reason="Record changed or assignment is processing; review again",
                    )
        except ForbiddenError:
            result.update(status="failed", reason="Record unavailable or not permitted")
        except Exception:  # noqa: BLE001 -- no raw database exceptions or personal data in batch results
            result.update(
                status="failed",
                reason="Assignment could not be completed; refresh to review before retrying",
            )
            try:
                current = await db[collection].find_one({"_id": ObjectId(rid)}, {"assignment_event_pending": 1}) if ObjectId.is_valid(rid) else None
            except PyMongoError:
                current = None
            if (current or {}).get("assignment_event_pending", {}).get("sequence") == operation:
                result["reason"] = (
                    "Assignment saved; linked synchronization is pending. Review ownership and retry this confirmed request."
                )
        results.append(result)
    return summary(results, preview_id)


def record_list(
    collection: Literal["leads", "applications"], ids: list[str]
) -> list[dict[str, str]]:
    return [
        {"collection": collection, "id": rid}
        for rid in dict.fromkeys(value.lower() for value in ids)
    ]
