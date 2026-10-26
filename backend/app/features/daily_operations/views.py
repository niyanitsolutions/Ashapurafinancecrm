import re
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import ReturnDocument

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.daily_operations.service import DailyOperationsService, calendar_values
from app.features.workflow_engine.constants import LoanStatus
from app.utils.datetime import ensure_utc, ist_date_to_utc_midnight, to_ist, utc_now


async def _crm_progress(
    service: DailyOperationsService,
    actor: User,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    status: str = "",
    employee: str = "",
    employee_name: str = "",
    bank: str = "",
    loan_type: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    old_days: int = 0,
    sort: str = "-updated_at",
) -> dict[str, Any]:
    await service.authorize(actor, "progress")
    query: dict[str, Any] = {"is_deleted": False, "case_type": "loan"}
    if actor.role != OWNER:
        query.update(
            assigned_to=await service.employee_id(actor), moved_to_loan_management_at={"$ne": None}
        )
    if employee:
        query["$and"] = [{"assigned_to": employee}]
    if employee_name:
        matching = (
            await service.db.employees.find(
                {
                    "display_name": {"$regex": re.escape(employee_name), "$options": "i"},
                    "is_deleted": False,
                },
                {"_id": 1},
            )
            .limit(100)
            .to_list(100)
        )
        query.setdefault("$and", []).append(
            {
                "$or": [
                    {"assigned_to": {"$in": [str(e["_id"]) for e in matching]}},
                    {"daily.employee_name": {"$regex": re.escape(employee_name), "$options": "i"}},
                ]
            }
        )
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

        query["daily_date"] = {}
        if date_from:
            query["daily_date"]["$gte"] = ist_date_to_utc_midnight(date_from)
        if date_to:
            query["daily_date"]["$lt"] = ist_date_to_utc_midnight(date_to + timedelta(days=1))
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
                {"$match": {"is_deleted": False, "case_type": "loan"}},
                {
                    "$lookup": {
                        "from": "daily_progress_entries",
                        "localField": "_id",
                        "foreignField": "_id",
                        "as": "daily",
                    }
                },
                {"$unwind": {"path": "$daily", "preserveNullAndEmptyArrays": True}},
                {"$match": {"daily.is_deleted": {"$ne": True}}},
                {"$project": {"daily.history": 0}},
                {
                    "$set": {
                        "updated_at": {"$ifNull": ["$daily.updated_at", "$updated_at"]},
                        "daily_date": {"$ifNull": ["$daily.date", "$created_at"]},
                    }
                },
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
        daily = calendar_values(case.get("daily") or {})
        items.append(
            {
                "id": str(case["_id"]),
                "case_code": case.get("case_code", ""),
                "application_id": case["application_id"],
                "lead_id": application.get("lead_id"),
                "date": daily.get("date") or to_ist(case["created_at"]).date().isoformat(),
                "created_at": case["created_at"],
                "case_id": str(case["_id"]),
                "source": "crm",
                "version": daily.get("version", 0),
                "employee_name": daily.get("employee_name", ""),
                "customer_name": customer.get("full_name", ""),
                "customer_number": customer.get("mobile", ""),
                "bank": details.get("bank_nbfc_name") or details.get("preferred_bank_name"),
                "loan_type": details.get("loan_type"),
                "assigned_to": case.get("assigned_to"),
                "canonical_status": case["current_status"],
                "status": daily.get("status") or case["current_status"],
                "remarks": daily.get("remarks", ""),
                "login_date": daily.get("login_date") or application.get("created_at"),
                "updated_at": case["updated_at"],
                "approved_amount": details.get("offered_amount"),
                "disbursed_amount": details.get("disbursed_amount")
                if case["current_status"] == "disbursed"
                else None,
                "disbursed_at": details.get("disbursed_at")
                if case["current_status"] == "disbursed"
                else None,
                "due_date": daily.get("due_date")
                or calendar_values(plans.get(str(case["_id"]), {})).get(
                    "due_date", case.get("next_follow_up_date")
                ),
                "next_action": daily.get("next_action")
                or plans.get(str(case["_id"]), {}).get("next_action"),
                "age_days": max(0, (utc_now() - ensure_utc(case["created_at"])).days),
            }
        )
    return {
        "items": items,
        "total": total,
        "metrics": metrics,
        "statuses": {s["_id"]: s["count"] for s in report["statuses"]},
    }


async def progress(service: DailyOperationsService, actor: User, **criteria: Any) -> dict[str, Any]:
    """Merge two bounded sources, following the existing document-collection list pattern."""
    page = criteria.pop("page", 1)
    size = criteria.pop("page_size", 20)
    take = page * size
    if take > 2000:
        raise ValidationError("Narrow the date range to browse more than 2,000 progress records.")
    crm = await _crm_progress(service, actor, page=1, page_size=take, **criteria)
    manual_criteria = {key: value for key, value in criteria.items() if key != "old_days"}
    manual_criteria["sort"] = manual_criteria.get("sort", "-updated_at").replace(
        "current_status", "status"
    )
    manual = await service.list_records(
        "progress", actor, page=1, page_size=take, **manual_criteria
    )
    items = [*crm["items"], *manual["items"]]
    field = criteria.get("sort", "-updated_at").lstrip("-")
    if field == "current_status":
        field = "status"

    def order(row: dict[str, Any]) -> str:
        value = row.get(field)
        return value.isoformat() if isinstance(value, datetime) else str(value or "")

    items.sort(
        key=lambda row: (order(row), row["id"]),
        reverse=criteria.get("sort", "-updated_at").startswith("-"),
    )
    ids = [
        ObjectId(row["assigned_to"])
        for row in items
        if row.get("assigned_to") and ObjectId.is_valid(row["assigned_to"])
    ]
    names = {
        str(e["_id"]): e["display_name"]
        for e in await service.db.employees.find(
            {"_id": {"$in": ids}, "is_deleted": False}, {"display_name": 1}
        )
        .limit(2000)
        .to_list(2000)
    }
    for row in items:
        row["employee_name"] = (
            row.get("employee_name") if row.get("source") != "crm" else ""
        ) or names.get(
            row.get("assigned_to"),
            "Owner" if actor.role == OWNER and row.get("assigned_to") == actor.require_id() else "",
        )
    return {
        "items": items[(page - 1) * size : page * size],
        "total": crm["total"] + manual["total"],
        "metrics": crm["metrics"],
        "statuses": crm["statuses"],
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
    data = {**payload.model_dump(exclude={"version"}), "user_id": session["user_id"]}
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
    from datetime import timedelta

    from app.features.auth.session_lifecycle import ensure_summary

    day = to_ist(payload.login_at).date()
    while day <= to_ist(payload.logout_at).date():
        await ensure_summary(service.db, session["user_id"], ist_date_to_utc_midnight(day))
        day += timedelta(days=1)
    return {"family_id": family_id, "version": payload.version + 1}


async def sessions(
    service: DailyOperationsService, actor: User, *, page: int = 1, page_size: int = 20,
    employee: str = "", employee_name: str = "", date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    from app.features.daily_operations.attendance import daily_sessions

    return await daily_sessions(service, actor, page=page, page_size=page_size,
                                employee=employee, employee_name=employee_name,
                                date_from=date_from, date_to=date_to)
