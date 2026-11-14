"""HR projections over existing employee, Daily Update and session records."""

import re
from datetime import date, datetime, time
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.daily_operations.attendance import daily_sessions, union_seconds
from app.features.daily_operations.service import DailyOperationsService
from app.features.employee.hr_documents import REQUIRED
from app.features.employee.hr_profile import HrProfiles
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ensure_utc, utc_now


def safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        "'" + text
        if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n"))
        else text
    )


class AttendancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apply_shift_window: bool = False
    deduct_configured_break: bool = False
    exclude_nonworking_days: bool = False
    exclude_holidays: bool = False
    version: int = Field(default=0, ge=0)
    shift_start: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    shift_end: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    break_minutes: int | None = Field(default=None, ge=0, le=720)
    holiday_dates: list[date] = Field(default_factory=list, max_length=366)
    working_weekdays: list[int] = Field(default_factory=list, max_length=7)


class HrReports(HrProfiles):
    async def policy(self, actor: Any) -> dict[str, Any]:
        if actor.role not in {"owner", "employee"}:
            raise ForbiddenError("Staff access required.")
        row = await self.db.employee_hr_settings.find_one({"_id": "default"})
        return {
            key: value
            for key, value in (row or {"version": 0, "configured": False}).items()
            if key != "_id"
        }

    async def save_policy(self, payload: AttendancePolicy, actor: Any) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only an owner can configure attendance policy.")
        if bool(payload.shift_start) != bool(payload.shift_end) or any(
            day < 0 or day > 6 for day in payload.working_weekdays
        ):
            raise ValidationError("Configure both shift boundaries and valid weekdays (0–6).")
        if payload.apply_shift_window and (
            not payload.shift_start
            or not payload.shift_end
            or payload.shift_end <= payload.shift_start
        ):
            raise ValidationError(
                "Applying shift windows requires an explicit same-day start and end. Overnight allocation is not configured."
            )
        if payload.deduct_configured_break and payload.break_minutes is None:
            raise ValidationError("Configure a break allowance before enabling its deduction.")
        if payload.exclude_nonworking_days and not payload.working_weekdays:
            raise ValidationError("Configure working weekdays before excluding other days.")
        previous = await self.db.employee_hr_settings.find_one({"_id": "default"})
        if (previous or {}).get("version", 0) != payload.version:
            raise ConflictError("Settings changed. Refresh before saving.")
        data = payload.model_dump(mode="json") | {
            "version": payload.version + 1,
            "configured": True,
            "updated_at": utc_now(),
            "updated_by": actor.require_id(),
        }
        if previous:
            changed = await self.db.employee_hr_settings.update_one(
                {"_id": "default", "version": payload.version}, {"$set": data}
            )
            if not changed.modified_count:
                raise ConflictError("Settings changed. Refresh before saving.")
        else:
            from pymongo.errors import DuplicateKeyError

            try:
                await self.db.employee_hr_settings.insert_one({"_id": "default", **data})
            except DuplicateKeyError:
                raise ConflictError("Settings changed. Refresh before saving.") from None
        await write_audit_log(
            self.db, event_type="employee_attendance_policy_changed", user_id=actor.require_id()
        )
        return data

    async def attendance(self, actor: Any, **criteria: Any) -> dict[str, Any]:
        # Reuse the exact Daily Update source and its own-record/RBAC/date projection.
        report = await daily_sessions(DailyOperationsService(self.db), actor, **criteria)
        policy = await self.policy(actor)
        ids = [ObjectId(row["employee_id"]) for row in report["items"]]
        employees = {
            str(row["_id"]): row
            async for row in self.db.employees.find({"_id": {"$in": ids}}, {"hr_leave_requests": 1})
        }
        for row in report["items"]:
            intervals = []
            events = []
            reconciliation = False
            open_session = False
            for session in row["sessions"]:
                observed = (
                    session["end_reason"] in {"manual_logout", "administrative_correction"}
                    and session.get("logout_at") is not None
                )
                events.append(
                    {
                        "id": session["id"] + ":in",
                        "type": "IN",
                        "session_reference": session["id"],
                        "at": session["login_at"],
                        "source": "existing_crm_session",
                    }
                )
                if observed:
                    events.append(
                        {
                            "id": session["id"] + ":out",
                            "type": "OUT",
                            "session_reference": session["id"],
                            "at": session["logout_at"],
                            "source": session["end_reason"],
                        }
                    )
                    intervals.append((session["segment_start_at"], session["segment_end_at"]))
                elif session["status"] == "active":
                    open_session = True
                else:
                    reconciliation = True
                session["observed_logout_at"] = session["logout_at"] if observed else None
                session["policy_end_at"] = None if observed else session["logout_at"]
                session["needs_reconciliation"] = not observed and session["status"] != "active"
            leave = [
                request
                for request in employees.get(row["employee_id"], {}).get("hr_leave_requests", [])
                if request["status"] == "approved"
                and request["start_date"] <= row["date"] <= request["end_date"]
            ]
            row.update(
                observed_session_seconds=union_seconds(intervals),
                needs_reconciliation=reconciliation,
                has_open_session=open_session,
                events=events,
                approved_leave=[
                    {
                        "id": request["id"],
                        "leave_type_name": request["leave_type_name"],
                        "calendar_days": request["calendar_days"],
                    }
                    for request in leave
                ],
            )
            adjusted = intervals
            if policy.get("apply_shift_window"):
                from zoneinfo import ZoneInfo

                from app.config.settings import get_settings

                zone = ZoneInfo(get_settings().timezone)
                shift_start = datetime.combine(
                    date.fromisoformat(row["date"]),
                    time.fromisoformat(policy["shift_start"]),
                    tzinfo=zone,
                )
                shift_end = datetime.combine(
                    date.fromisoformat(row["date"]),
                    time.fromisoformat(policy["shift_end"]),
                    tzinfo=zone,
                )
                adjusted = [
                    (
                        max(ensure_utc(start), ensure_utc(shift_start)),
                        min(ensure_utc(end), ensure_utc(shift_end)),
                    )
                    for start, end in intervals
                ]
            adjusted_seconds = union_seconds(adjusted)
            if policy.get("deduct_configured_break"):
                adjusted_seconds = max(0, adjusted_seconds - policy["break_minutes"] * 60)
            if (
                policy.get("exclude_holidays") and row["date"] in policy.get("holiday_dates", [])
            ) or (
                policy.get("exclude_nonworking_days")
                and date.fromisoformat(row["date"]).weekday() not in policy["working_weekdays"]
            ):
                adjusted_seconds = 0
            row["policy_adjusted_observed_seconds"] = (
                None
                if reconciliation or open_session or not policy.get("configured")
                else adjusted_seconds
            )
            row["observed_logout_at"] = max(
                (
                    session["observed_logout_at"]
                    for session in row["sessions"]
                    if session["observed_logout_at"]
                ),
                default=None,
            )
        report["policy"] = policy
        report["duration_note"] = (
            "Observed session time unions overlapping sessions. Open or unobserved OUT events require reconciliation. Session time is not payable working time."
        )
        return report

    async def report(
        self,
        section: str,
        actor: Any,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        status: str = "",
        employee_id: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 200:
            raise ValidationError("Use pagination between 1 and 200 records.")
        if section not in {
            "directory",
            "profile-completion",
            "documents",
            "pending-documents",
            "leaves",
            "edits",
        }:
            raise ValidationError("Unknown employee report.")
        if actor.role not in {"owner", "employee"}:
            raise ForbiddenError("Staff access required.")
        if actor.role != "owner" and section not in {"leaves", "edits"}:
            raise ForbiddenError("Owner access required for this report.")
        query: dict[str, Any] = {"is_deleted": False}
        if actor.role != "owner":
            query["user_id"] = actor.require_id()
        if employee_id:
            if not ObjectId.is_valid(employee_id):
                raise ValidationError("Invalid employee filter.")
            query["_id"] = ObjectId(employee_id)
        if search:
            query["$or"] = [
                {key: {"$regex": re.escape(search), "$options": "i"}}
                for key in ("display_name", "employee_code", "email")
            ]
        if date_from and date_to and date_from > date_to:
            raise ValidationError("Use an ordered date range.")
        if section in {"leaves", "edits"}:
            field = "hr_leave_requests" if section == "leaves" else "hr_edit_requests"
            match: dict[str, Any] = {}
            if status:
                match[field + ".status"] = status
            if section == "leaves":
                if date_from:
                    match[field + ".end_date"] = {"$gte": date_from.isoformat()}
                if date_to:
                    match[field + ".start_date"] = {"$lte": date_to.isoformat()}
            else:
                from app.utils.datetime import ist_date_range_to_utc_bounds

                lower, upper = ist_date_range_to_utc_bounds(date_from, date_to)
                if lower or upper:
                    match[field + ".requested_at"] = {
                        **({"$gte": lower} if lower else {}),
                        **({"$lt": upper} if upper else {}),
                    }
            pipeline = [
                {"$match": query},
                {"$unwind": "$" + field},
                {"$match": match},
                {
                    "$facet": {
                        "items": [
                            {"$sort": {field + ".requested_at": -1}},
                            {"$skip": (page - 1) * page_size},
                            {"$limit": page_size},
                        ],
                        "total": [{"$count": "value"}],
                    }
                },
            ]
            result = (await self.db.employees.aggregate(pipeline).to_list(1))[0]
            rows = []
            for employee in result["items"]:
                request = employee[field]
                rows.append(
                    {
                        "employee_id": str(employee["_id"]),
                        "employee_code": employee["employee_code"],
                        "employee_name": employee["display_name"],
                        **{
                            key: request.get(key)
                            for key in (
                                "id",
                                "status",
                                "requested_at",
                                "reviewed_at",
                                "start_date",
                                "end_date",
                                "leave_type_name",
                                "calendar_days",
                                "reason",
                                "review_reason",
                            )
                        },
                    }
                )
            return {"items": rows, "total": result["total"][0]["value"] if result["total"] else 0}
        categories = REQUIRED | {
            "relieving_letter",
            "experience_letter",
            "experience_certificate",
            "other",
        }
        if section == "pending-documents":
            query.setdefault("$and", []).append(
                {
                    "$or": [
                        {f"hr_documents.{category}.status": "pending_verification"}
                        for category in categories
                    ]
                }
            )
        elif status:
            if section == "directory":
                query["status"] = status
            elif section == "documents":
                query.setdefault("$and", []).append(
                    {
                        "$or": [
                            {f"hr_documents.{category}": {"$exists": False}}
                            if status == "not_uploaded"
                            else {f"hr_documents.{category}.status": status}
                            for category in categories
                        ]
                    }
                )
            elif status == "incomplete":
                query.setdefault("$and", []).append(
                    {
                        "$or": [
                            {"onboarding.status": "incomplete"},
                            {"onboarding.status": {"$exists": False}},
                        ]
                    }
                )
            else:
                query["onboarding.status"] = status
        total = await self.db.employees.count_documents(query)
        rows = []
        async for employee in (
            self.db.employees.find(query)
            .sort("employee_code", 1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        ):
            documents = employee.get("hr_documents", {})
            required = REQUIRED | (
                {"relieving_letter", "experience_letter"}
                if not employee.get("onboarding", {}).get("profile", {}).get("fresher", True)
                else set()
            )
            pending = [
                key
                for key, value in documents.items()
                if value.get("status") == "pending_verification"
            ]
            approved = [
                key for key, value in documents.items() if value.get("status") == "approved"
            ]
            rows.append(
                {
                    "employee_id": str(employee["_id"]),
                    "employee_code": employee["employee_code"],
                    "employee_name": employee["display_name"],
                    "email": employee["email"],
                    "mobile": employee["mobile"],
                    "account_status": employee["status"],
                    "profile_status": employee.get("onboarding", {}).get("status", "incomplete"),
                    "pending_documents": ", ".join(sorted(pending)),
                    "approved_document_count": len(approved),
                    "missing_documents": ", ".join(sorted(required - set(documents))),
                }
            )
        return {"items": rows, "total": total}
