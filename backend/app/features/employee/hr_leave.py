"""Explicit leave policies and atomically reserved calendar days per employee."""

from datetime import date, timedelta
from typing import Any, Self

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.employee.hr_notifications import record_event as write_audit_log
from app.features.employee.hr_profile import HrProfiles
from app.utils.datetime import utc_now


class LeaveTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    annual_calendar_day_limit: int | None = Field(default=None, ge=0, le=366)
    # Required explicit acknowledgment; no paid entitlement or working-day conversion.
    counting_method: str = Field(pattern="^calendar_days$")
    is_active: bool = True
    version: int = Field(default=0, ge=0)


class LeaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    leave_type_id: str = Field(pattern=r"^[a-fA-F0-9]{24}$")
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 365:
            raise ValueError("Use an ordered leave range of at most 366 calendar days.")
        if self.start_date.year != self.end_date.year:
            raise ValueError("Submit separate leave requests for different calendar years.")
        return self


class HrLeave(HrProfiles):
    async def types(self, actor: Any) -> list[dict[str, Any]]:
        if actor.role not in {"owner", "employee"}:
            raise ForbiddenError("Staff access required.")
        return [
            {key: value for key, value in row.items() if key != "_id"} | {"id": str(row["_id"])}
            async for row in self.db.employee_leave_types.find({"company_id": "default"}).sort(
                "name", 1
            )
        ]

    async def save_type(
        self, payload: LeaveTypeInput, actor: Any, option_id: str | None = None
    ) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only an owner can configure leave policies.")
        values = payload.model_dump(exclude={"version"}) | {
            "normalized_name": " ".join(payload.name.split()).casefold(),
            "company_id": "default",
            "updated_at": utc_now(),
            "updated_by": actor.require_id(),
        }
        try:
            if option_id:
                if not ObjectId.is_valid(option_id):
                    raise ValidationError("Invalid leave type.")
                row = await self.db.employee_leave_types.find_one_and_update(
                    {
                        "_id": ObjectId(option_id),
                        "company_id": "default",
                        "version": payload.version,
                    },
                    {"$set": values, "$inc": {"version": 1}},
                    return_document=ReturnDocument.AFTER,
                )
                if not row:
                    raise ConflictError("Leave policy changed. Refresh before saving.")
            else:
                row = values | {"_id": ObjectId(), "version": 1, "created_at": utc_now()}
                await self.db.employee_leave_types.insert_one(row)
        except DuplicateKeyError:
            raise ConflictError("A leave type with this name already exists.") from None
        await write_audit_log(
            self.db,
            event_type="employee_leave_type_changed",
            user_id=actor.require_id(),
            metadata={"leave_type_id": str(row["_id"])},
        )
        return {key: value for key, value in row.items() if key != "_id"} | {"id": str(row["_id"])}

    async def apply(self, employee_id: str, payload: LeaveInput, actor: Any) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor)
        policy = await self.db.employee_leave_types.find_one(
            {"_id": ObjectId(payload.leave_type_id), "company_id": "default", "is_active": True}
        )
        if not policy:
            raise ValidationError("Select an active configured leave type.")
        days = [
            (payload.start_date + timedelta(days=i)).isoformat()
            for i in range((payload.end_date - payload.start_date).days + 1)
        ]
        reservations = employee.get("hr_leave_reservations", {})
        if any(day in reservations for day in days):
            raise ConflictError("Leave overlaps an existing pending or approved request.")
        requests = employee.get("hr_leave_requests", [])
        consumed = sum(
            row["calendar_days"]
            for row in requests
            if row["status"] in {"pending", "approved"}
            and row["leave_type_id"] == payload.leave_type_id
            and row["start_date"][:4] == str(payload.start_date.year)
        )
        limit = policy.get("annual_calendar_day_limit")
        if limit is not None and consumed + len(days) > limit:
            raise ValidationError(
                "This request exceeds the explicitly configured calendar-day leave balance."
            )
        oid = str(ObjectId())
        now = utc_now()
        request = {
            "id": oid,
            "employee_id": str(employee["_id"]),
            "employee_name": employee["display_name"],
            "leave_type_id": payload.leave_type_id,
            "leave_type_name": policy["name"],
            "policy_version": policy["version"],
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
            "calendar_days": len(days),
            "counting_method": "calendar_days",
            "reason": payload.reason,
            "status": "pending",
            "requested_by": actor.require_id(),
            "requested_at": now,
            "history": [{"status": "pending", "at": now, "actor_id": actor.require_id()}],
        }
        changed = await self.commit(
            {
                "_id": employee["_id"],
                "is_deleted": False,
                "hr_leave_requests": employee.get("hr_leave_requests"),
                "hr_leave_reservations": employee.get("hr_leave_reservations"),
            },
            {
                "$set": {
                    "hr_leave_requests": requests + [request],
                    "hr_leave_reservations": reservations | {day: oid for day in days},
                }
            },
            actor,
            "employee_leave_applied",
            {"employee_id": str(employee["_id"]), "request_id": oid},
        )
        if not changed:
            raise ConflictError("Another leave request changed. Refresh and try again.")
        await write_audit_log(
            self.db,
            event_type="employee_leave_applied",
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"]), "request_id": oid},
        )
        return request

    async def decide_leave(
        self, employee_id: str, request_id: str, decision: str, reason: str, actor: Any
    ) -> dict[str, Any]:
        employee = await self.employee(employee_id, actor, review=decision != "cancelled")
        if decision not in {"approved", "rejected", "cancelled"}:
            raise ValidationError("Invalid leave decision.")
        requests = employee.get("hr_leave_requests", [])
        request = next(
            (row for row in requests if row["id"] == request_id and row["status"] == "pending"),
            None,
        )
        if not request:
            raise ConflictError("Only pending leave can be reviewed or cancelled.")
        if decision == "rejected" and not reason.strip():
            raise ValidationError("A rejection reason is required.")
        now = utc_now()
        decided = request | {
            "status": decision,
            "attendance_projection_pending": decision == "approved",
            "reviewed_by": actor.require_id(),
            "reviewed_at": now,
            "review_reason": reason.strip(),
            "history": request["history"]
            + [
                {
                    "status": decision,
                    "at": now,
                    "reason": reason.strip(),
                    "actor_id": actor.require_id(),
                }
            ],
        }
        reservations = employee.get("hr_leave_reservations", {})
        changed = await self.commit(
            {"_id": employee["_id"], "is_deleted": False, "hr_leave_requests": requests},
            {
                "$set": {
                    "hr_leave_requests": [
                        decided if row["id"] == request_id else row for row in requests
                    ],
                    "hr_leave_reservations": reservations
                    if decision == "approved"
                    else {day: oid for day, oid in reservations.items() if oid != request_id},
                }
            },
            actor,
            "employee_leave_" + decision,
            {"employee_id": str(employee["_id"]), "request_id": request_id},
        )
        if not changed:
            raise ConflictError("Leave changed. Refresh before reviewing.")
        if decision == "approved":
            await project_approved_leave(self.db, changed)
        await write_audit_log(
            self.db,
            event_type="employee_leave_" + decision,
            user_id=actor.require_id(),
            metadata={"employee_id": str(employee["_id"]), "request_id": request_id},
        )
        return dict(decided)


async def project_approved_leave(db: Any, employee: dict[str, Any]) -> None:
    """Idempotently repair attendance projections from committed leave decisions."""
    from app.features.auth.session_lifecycle import ensure_summary
    from app.utils.datetime import ist_date_to_utc_midnight

    for request in employee.get("hr_leave_requests", []):
        if request.get("status") != "approved" or not request.get("attendance_projection_pending"):
            continue
        start = date.fromisoformat(request["start_date"])
        for offset in range(request["calendar_days"]):
            key = await ensure_summary(
                db, employee["user_id"], ist_date_to_utc_midnight(start + timedelta(days=offset))
            )
            await db.attendance_days.update_one(
                {"_id": key}, {"$addToSet": {"approved_leave_request_ids": request["id"]}}
            )
        await db.employees.update_one(
            {
                "_id": employee["_id"],
                "hr_leave_requests": {"$elemMatch": {"id": request["id"], "status": "approved"}},
            },
            {"$set": {"hr_leave_requests.$.attendance_projection_pending": False}},
        )
