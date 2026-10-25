import re
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import ReturnDocument

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.daily_operations.service import DailyOperationsService, calendar_values
from app.features.workflow_engine.constants import LoanStatus
from app.utils.datetime import ensure_utc, ist_date_to_utc_midnight, to_ist, utc_now


async def progress(
    service: DailyOperationsService,
    actor: User,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    status: str = "",
    employee: str = "",
    bank: str = "",
    loan_type: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    old_days: int = 0,
    sort: str = "-updated_at",
) -> dict[str, Any]:
    await service.authorize(actor, "progress")
    if not await PermissionEngine(service.db).has_permission(
        actor, module="loan_management", resource="applications", action="view"
    ):
        raise ForbiddenError("Loan visibility permission is required.")
    query: dict[str, Any] = {"is_deleted": False, "case_type": "loan"}
    if actor.role != OWNER:
        query.update(
            assigned_to=await service.employee_id(actor), moved_to_loan_management_at={"$ne": None}
        )
    if employee:
        query["$and"] = [{"assigned_to": employee}]
    for key, value in (
        ("current_status", status),
        ("loan_details.bank_nbfc_name", bank),
        ("loan_details.loan_type", loan_type),
    ):
        if value:
            query[key] = value
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Start date must be before end date.")
    if date_from or date_to:
        from datetime import timedelta

        query["created_at"] = {}
        if date_from:
            query["created_at"]["$gte"] = ist_date_to_utc_midnight(date_from)
        if date_to:
            query["created_at"]["$lt"] = ist_date_to_utc_midnight(date_to + timedelta(days=1))
    if old_days:
        from datetime import timedelta

        query.setdefault("$and", []).extend(
            [
                {"created_at": {"$lte": utc_now() - timedelta(days=old_days)}},
                {"current_status": {"$nin": list(LoanStatus.TERMINAL)}},
            ]
        )
    if search:
        query["case_code"] = {"$regex": re.escape(search), "$options": "i"}
    field = sort.lstrip("-")
    if field not in {"created_at", "updated_at", "current_status"}:
        raise ValidationError("Unsupported sort column.")
    collection = service.db.application_workflows
    report = (
        await collection.aggregate(
            [
                {"$match": query},
                {
                    "$facet": {
                        "items": [
                            {"$sort": {field: -1 if sort.startswith("-") else 1, "_id": 1}},
                            {"$skip": (page - 1) * page_size},
                            {"$limit": page_size},
                        ],
                        "metrics": [
                            {
                                "$group": {
                                    "_id": None,
                                    "total": {"$sum": 1},
                                    "approved_amount": {"$sum": "$loan_details.offered_amount"},
                                    "disbursed_amount": {
                                        "$sum": {
                                            "$cond": [
                                                {"$eq": ["$current_status", "disbursed"]},
                                                "$loan_details.disbursed_amount",
                                                0,
                                            ]
                                        }
                                    },
                                }
                            }
                        ],
                        "statuses": [{"$group": {"_id": "$current_status", "count": {"$sum": 1}}}],
                    }
                },
            ]
        ).to_list(1)
    )[0]
    cases = report["items"]
    metrics = (
        report["metrics"][0]
        if report["metrics"]
        else {"total": 0, "approved_amount": 0, "disbursed_amount": 0}
    )
    metrics.pop("_id", None)
    total = metrics["total"]
    application_ids = [ObjectId(c["application_id"]) for c in cases]
    applications = {
        str(a["_id"]): a
        for a in await service.db.applications.find(
            {"_id": {"$in": application_ids}, "is_deleted": False},
            {"lead_id": 1, "customer_id": 1, "created_at": 1},
        ).to_list(page_size)
    }
    customer_ids = [
        ObjectId(a["customer_id"]) for a in applications.values() if a.get("customer_id")
    ]
    customers = {
        str(c["_id"]): c
        for c in await service.db.customers.find(
            {"_id": {"$in": customer_ids}, "is_deleted": False}, {"full_name": 1, "mobile": 1}
        ).to_list(page_size)
    }
    plans = {
        entry["_id"]: entry
        for entry in await service.db.daily_follow_ups.aggregate(
            [
                {
                    "$match": {
                        "case_id": {"$in": [str(c["_id"]) for c in cases]},
                        "is_deleted": False,
                    }
                },
                {"$sort": {"updated_at": -1, "_id": -1}},
                {
                    "$group": {
                        "_id": "$case_id",
                        "next_action": {"$first": "$next_action"},
                        "due_date": {"$first": "$due_date"},
                    }
                },
            ]
        ).to_list(page_size)
    }
    items = []
    for case in cases:
        application = applications.get(case["application_id"], {})
        customer = customers.get(application.get("customer_id", ""), {})
        details = case.get("loan_details") or {}
        items.append(
            {
                "id": str(case["_id"]),
                "case_code": case.get("case_code", ""),
                "application_id": case["application_id"],
                "lead_id": application.get("lead_id"),
                "date": to_ist(case["created_at"]).date().isoformat(),
                "customer_name": customer.get("full_name", ""),
                "customer_number": customer.get("mobile", ""),
                "bank": details.get("bank_nbfc_name") or details.get("preferred_bank_name"),
                "loan_type": details.get("loan_type"),
                "assigned_to": case.get("assigned_to"),
                "status": case["current_status"],
                "login_date": application.get("created_at"),
                "updated_at": case["updated_at"],
                "approved_amount": details.get("offered_amount"),
                "disbursed_amount": details.get("disbursed_amount")
                if case["current_status"] == "disbursed"
                else None,
                "disbursed_at": details.get("disbursed_at")
                if case["current_status"] == "disbursed"
                else None,
                "due_date": calendar_values(plans.get(str(case["_id"]), {})).get(
                    "due_date", case.get("next_follow_up_date")
                ),
                "next_action": plans.get(str(case["_id"]), {}).get("next_action"),
                "age_days": max(0, (utc_now() - ensure_utc(case["created_at"])).days),
            }
        )
    return {
        "items": items,
        "total": total,
        "metrics": metrics,
        "statuses": {s["_id"]: s["count"] for s in report["statuses"]},
    }


class SessionCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    login_at: datetime
    logout_at: datetime
    reason: str = Field(min_length=5, max_length=1000)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_times(self) -> "SessionCorrection":
        if not self.login_at.tzinfo or not self.logout_at.tzinfo:
            raise ValueError("Correction timestamps require an explicit timezone.")
        if self.logout_at < self.login_at or self.logout_at > utc_now():
            raise ValueError("Logout must be after login and cannot be in the future.")
        return self


async def correct_session(
    service: DailyOperationsService,
    actor: User,
    family_id: str,
    payload: SessionCorrection,
    import_key: str | None = None,
) -> dict[str, Any]:
    await service.authorize(actor, "sessions", "edit")
    if actor.role != OWNER:
        raise ForbiddenError("Only an Owner can correct recorded sessions.")
    session = await service.db.sessions.find_one({"family_id": family_id, "is_deleted": False})
    if not session or not await service.db.employees.find_one(
        {"user_id": session["user_id"], "is_deleted": False}
    ):
        raise NotFoundError("Employee session not found.")
    data = payload.model_dump(exclude={"version"})
    event = {**data, "actor_id": actor.require_id(), "at": utc_now(), "import_key": import_key}
    collection = service.db.session_corrections
    if payload.version == 0:
        from pymongo.errors import DuplicateKeyError

        try:
            await collection.insert_one(
                {"_id": family_id, **data, "version": 1, "history": [event]}
            )
        except DuplicateKeyError:
            raise ConflictError("A correction already exists; reload before editing.") from None
    else:
        result = await collection.find_one_and_update(
            {"_id": family_id, "version": payload.version, "history.999": {"$exists": False}},
            {"$set": data, "$inc": {"version": 1}, "$push": {"history": event}},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise ConflictError("Correction changed or its history limit was reached; reload.")
    return {"family_id": family_id, "version": payload.version + 1}


async def sessions(
    service: DailyOperationsService,
    actor: User,
    *,
    page: int = 1,
    page_size: int = 20,
    employee: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    await service.authorize(actor, "sessions")
    query: dict[str, Any] = {"is_deleted": False}
    if actor.role != OWNER:
        query["user_id"] = actor.require_id()
    pipeline: list[dict[str, Any]] = [
        {"$match": query},
        {"$sort": {"updated_at": 1, "_id": 1}},
        {
            "$group": {
                "_id": "$family_id",
                "user_id": {"$first": "$user_id"},
                "login_at": {"$min": "$login_at"},
                "logout_at": {"$max": "$logout_at"},
                "status": {"$last": "$status"},
            }
        },
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
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Start date must be before end date.")
    if date_from or date_to:
        from datetime import timedelta

        dates: dict[str, Any] = {}
        if date_from:
            dates["$gte"] = ist_date_to_utc_midnight(date_from)
        if date_to:
            dates["$lt"] = ist_date_to_utc_midnight(date_to + timedelta(days=1))
        pipeline.append({"$match": {"login_at": dates}})
    pipeline.append(
        {
            "$facet": {
                "items": [
                    {"$sort": {"login_at": -1, "_id": 1}},
                    {"$skip": (page - 1) * page_size},
                    {"$limit": page_size},
                ],
                "total": [{"$count": "value"}],
            }
        }
    )
    result = (await service.db.sessions.aggregate(pipeline).to_list(1))[0]
    corrections = {
        c["_id"]: c
        for c in await service.db.session_corrections.find(
            {"_id": {"$in": [s["_id"] for s in result["items"]]}}
        ).to_list(page_size)
    }
    items = []
    for session in result["items"]:
        correction = corrections.get(session["_id"], {})
        login = correction.get("login_at", session["login_at"])
        logout = correction.get("logout_at", session.get("logout_at"))
        items.append(
            {
                "id": session["_id"],
                "employee_name": session["employee"]["display_name"],
                "employee_id": str(session["employee"]["_id"]),
                "date": to_ist(login).date().isoformat(),
                "login_at": login,
                "logout_at": logout,
                "status": session["status"],
                "recorded_seconds": max(
                    0, int((ensure_utc(logout) - ensure_utc(login)).total_seconds())
                )
                if logout
                else None,
                "corrected": bool(correction),
                "correction_version": correction.get("version", 0),
                "original_login_at": session["login_at"],
                "original_logout_at": session.get("logout_at"),
            }
        )
    return {"items": items, "total": result["total"][0]["value"] if result["total"] else 0}
