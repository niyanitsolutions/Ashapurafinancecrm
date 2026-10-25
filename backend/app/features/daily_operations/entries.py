"""Simple daily rows and annotations. Never creates or deletes an actual CRM loan."""

import re
from typing import TYPE_CHECKING, Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.daily_operations.schemas import DeleteRecord, ProgressInput
from app.shared.base_document import BaseDocument
from app.utils.datetime import to_ist, utc_now

if TYPE_CHECKING:
    from app.features.daily_operations.service import DailyOperationsService


async def assignee(
    service: "DailyOperationsService", actor: User, requested: str | None, name: str = ""
) -> dict[str, Any]:
    own_id = await service.employee_id(actor)
    if not requested and name:
        matches = (
            await service.db.employees.find(
                {
                    "display_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
                    "is_deleted": False,
                    "status": "active",
                },
                {"_id": 1},
            )
            .limit(2)
            .to_list(2)
        )
        if len(matches) > 1:
            raise ValidationError(
                "More than one employee has that name. Choose a unique employee account."
            )
        if matches:
            requested = str(matches[0]["_id"])
    selected = requested or own_id
    if actor.role != OWNER and selected != own_id:
        raise ForbiddenError("You can enter updates only for your own employee account.")
    employee = await service.db.employees.find_one(
        {"_id": ObjectId(selected), "is_deleted": False, "status": "active"}
    )
    if (
        actor.role != OWNER
        and employee
        and name
        and name.casefold() != employee["display_name"].casefold()
    ):
        other_name = await service.db.employees.find_one(
            {
                "display_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
                "is_deleted": False,
                "status": "active",
            },
            {"_id": 1},
        )
        if other_name:
            raise ForbiddenError("Choose your own employee name; another account cannot be used.")
    owner = (
        await service.db.users.find_one(
            {"_id": ObjectId(selected), "role": OWNER, "status": "active", "is_deleted": False}
        )
        if not employee and actor.role == OWNER
        else None
    )
    if not employee and not owner and selected != actor.require_id():
        raise ValidationError("Choose an active employee or leave the name as a manual entry.")
    return {
        "assigned_to": selected,
        "employee_name": name or (employee["display_name"] if employee else "Owner"),
    }


async def case_row(service: "DailyOperationsService", actor: User, case_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(case_id):
        raise NotFoundError("Loan record not found.")
    case = await service.db.application_workflows.find_one(
        {"_id": ObjectId(case_id), "case_type": "loan", "is_deleted": False}
    )
    if not case:
        raise NotFoundError("Loan record not found.")
    if actor.role != OWNER and (
        case.get("assigned_to") != await service.employee_id(actor)
        or not case.get("moved_to_loan_management_at")
    ):
        raise ForbiddenError("This loan record is not assigned to you.")
    application = await service.db.applications.find_one(
        {"_id": ObjectId(case["application_id"]), "is_deleted": False}
    )
    customer = (
        await service.db.customers.find_one(
            {"_id": ObjectId(case["customer_id"]), "is_deleted": False}
        )
        if case.get("customer_id")
        else None
    )
    lead = (
        await service.db.leads.find_one(
            {"_id": ObjectId(application["lead_id"]), "is_deleted": False}
        )
        if application and application.get("lead_id")
        else None
    )
    details = case.get("loan_details") or {}
    return {
        "case_id": case_id,
        "application_id": case["application_id"],
        "customer_name": (customer or lead or {}).get("full_name", ""),
        "customer_number": (customer or lead or {}).get("mobile", ""),
        "bank": details.get("bank_nbfc_name") or details.get("preferred_bank_name") or "",
        "loan_type": details.get("loan_type") or "",
        "assigned_to": case.get("assigned_to"),
        "canonical_status": case["current_status"],
        "case_code": case.get("case_code", ""),
        "date": to_ist(case["created_at"]).date().isoformat(),
        "login_date": to_ist(application["created_at"]).date().isoformat() if application else None,
        "approved_amount": details.get("offered_amount"),
        "disbursed_amount": details.get("disbursed_amount")
        if case["current_status"] == "disbursed"
        else None,
        "disbursed_at": details.get("disbursed_at")
        if case["current_status"] == "disbursed"
        else None,
        "disbursed_reference": details.get("disbursed_reference"),
    }


async def get_progress(
    service: "DailyOperationsService", actor: User, record_id: str
) -> dict[str, Any]:
    await service.authorize(actor, "progress")
    if not ObjectId.is_valid(record_id):
        raise NotFoundError("Daily entry not found.")
    entry: dict[str, Any] | None = await service.db.daily_progress_entries.find_one(
        {"_id": ObjectId(record_id)}
    )
    if entry and entry.get("is_deleted"):
        raise NotFoundError("Daily entry not found.")
    if entry and not entry.get("case_id"):
        if actor.role != OWNER and entry.get("assigned_to") != await service.employee_id(actor):
            raise ForbiddenError("This daily entry is not assigned to you.")
        return entry
    canonical = await case_row(service, actor, record_id)
    stage_events = (
        await service.db.application_status_history.find(
            {"application_workflow_id": record_id, "is_deleted": False},
            {"created_at": 1, "created_by": 1, "from_status": 1, "to_status": 1, "remarks": 1},
        )
        .sort("created_at", -1)
        .limit(250)
        .to_list(250)
    )
    history = [
        *(entry or {}).get("history", []),
        *[
            {
                "at": event["created_at"],
                "actor_id": event.get("created_by"),
                "before": {"loan_stage": event.get("from_status")},
                "after": {
                    "loan_stage": event.get("to_status"),
                    "remarks": event.get("remarks") or "",
                },
            }
            for event in stage_events
        ],
    ]
    history.sort(key=lambda event: str(event["at"]))
    employee = (
        await service.db.employees.find_one(
            {"_id": ObjectId(canonical["assigned_to"]), "is_deleted": False}, {"display_name": 1}
        )
        if canonical.get("assigned_to") and ObjectId.is_valid(canonical["assigned_to"])
        else None
    )
    return {
        **(entry or {}),
        **canonical,
        "_id": ObjectId(record_id),
        "source": "crm",
        "date": (entry or {}).get("date", canonical["date"]),
        "login_date": (entry or {}).get("login_date") or canonical.get("login_date"),
        "employee_name": employee["display_name"]
        if employee
        else "Owner"
        if canonical.get("assigned_to")
        else "Unassigned",
        "status": (entry or {}).get("status", canonical["canonical_status"]),
        "version": (entry or {}).get("version", 0),
        "history": history,
    }


async def progress_data(
    service: "DailyOperationsService", actor: User, payload: ProgressInput
) -> dict[str, Any]:
    from app.features.daily_operations.service import stored_values

    canonical = await case_row(service, actor, payload.case_id) if payload.case_id else None
    data = stored_values(payload)
    data["source"] = "crm" if canonical else "manual"
    data.update(
        await assignee(
            service,
            actor,
            payload.assigned_to or (canonical or {}).get("assigned_to"),
            "" if canonical else payload.employee_name,
        )
    )
    if canonical:
        if "status" not in payload.model_fields_set:
            data["status"] = canonical["canonical_status"]
        if payload.assigned_to and payload.assigned_to != canonical["assigned_to"]:
            raise ValidationError("Change the CRM loan's assignment in Loan Management.")
        for field in ("approved_amount", "disbursed_amount"):
            if getattr(payload, field) is not None and getattr(payload, field) != canonical[field]:
                raise ValidationError(
                    "Official loan amounts must be updated through Loan Management."
                )
        data.update(
            {
                key: canonical[key]
                for key in (
                    "customer_name",
                    "customer_number",
                    "bank",
                    "loan_type",
                    "assigned_to",
                    "approved_amount",
                    "disbursed_amount",
                    "disbursed_at",
                )
            }
        )
    return data


async def save_progress(
    service: "DailyOperationsService",
    actor: User,
    payload: ProgressInput,
    record_id: str | None = None,
    version: int | None = None,
    import_key: str | None = None,
) -> dict[str, Any]:
    from app.features.daily_operations.service import public

    await service.authorize(actor, "progress", "edit" if record_id else "create")
    current = await get_progress(service, actor, record_id) if record_id else None
    if current and payload.case_id != current.get("case_id"):
        raise ValidationError("The linked CRM loan cannot be changed.")
    data = await progress_data(service, actor, payload)
    target_id = (
        ObjectId(payload.case_id or record_id) if payload.case_id or record_id else ObjectId()
    )
    old: dict[str, Any] | None = await service.db.daily_progress_entries.find_one(
        {"_id": target_id}
    )
    if old and not record_id:
        raise ConflictError("This loan already has an update. Use Edit on its row.")
    if (
        (old and old.get("is_deleted"))
        or (old and old["version"] != version)
        or (not old and record_id and version != 0)
    ):
        raise ConflictError("This row changed. Reload it before saving.")
    now = utc_now()
    event = {
        "actor_id": actor.require_id(),
        "at": now,
        "before": {k: old.get(k) for k in data} if old else None,
        "after": data,
        "import_key": import_key,
    }
    if old:
        if len(old.get("history", [])) >= 250:
            raise ConflictError("History is full. Ask the Owner to archive this row.")
        result = await service.db.daily_progress_entries.find_one_and_update(
            {"_id": target_id, "version": version, "is_deleted": False},
            {
                "$set": {**data, "updated_at": now, "updated_by": actor.require_id()},
                "$inc": {"version": 1},
                "$push": {"history": event},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise ConflictError("This row changed. Reload it before saving.")
        return public(result)
    doc = {
        **BaseDocument(created_by=actor.require_id()).model_dump(exclude={"id"}),
        **data,
        "_id": target_id,
        "history": [event],
    }
    if import_key:
        doc["import_key"] = import_key
    try:
        await service.db.daily_progress_entries.insert_one(doc)
    except DuplicateKeyError:
        raise ConflictError("This row changed. Reload it before saving.") from None
    return public(doc)


async def remove(
    service: "DailyOperationsService", actor: User, area: str, record_id: str, payload: DeleteRecord
) -> dict[str, Any]:
    from app.features.daily_operations.service import COLLECTIONS

    await service.authorize(actor, area, "delete")
    if actor.role != OWNER:
        raise ForbiddenError("Only the Owner can delete daily records.")
    now = utc_now()
    event = {
        "actor_id": actor.require_id(),
        "at": now,
        "action": "deleted",
        "reason": payload.reason,
    }
    if area == "sessions":
        session = await service.db.sessions.find_one({"family_id": record_id, "is_deleted": False})
        if not session or not await service.db.employees.find_one(
            {"user_id": session["user_id"], "is_deleted": False}
        ):
            raise NotFoundError("Employee session not found.")
        try:
            await service.db.daily_session_visibility.insert_one(
                {
                    "_id": record_id,
                    "is_deleted": True,
                    "deleted_by": actor.require_id(),
                    "deleted_at": now,
                    "history": [event],
                }
            )
        except DuplicateKeyError:
            raise ConflictError("This session is already removed from Daily Update.") from None
    else:
        current = (
            await get_progress(service, actor, record_id)
            if area == "progress"
            else await service.db[COLLECTIONS[area]].find_one(
                {"_id": ObjectId(record_id), "is_deleted": False}
            )
            if ObjectId.is_valid(record_id)
            else None
        )
        if not current:
            raise NotFoundError("Daily record not found.")
        collection = service.db[COLLECTIONS[area]]
        if current.get("version", 0) != payload.version:
            raise ConflictError("This row changed. Reload before deleting.")
        if area == "progress" and current.get("version") == 0:
            try:
                await collection.insert_one(
                    {
                        **BaseDocument(created_by=actor.require_id()).model_dump(exclude={"id"}),
                        "_id": current["_id"],
                        "case_id": record_id,
                        "is_deleted": True,
                        "deleted_by": actor.require_id(),
                        "deleted_at": now,
                        "history": [event],
                    }
                )
            except DuplicateKeyError:
                raise ConflictError("This row changed. Reload before deleting.") from None
        else:
            result = await collection.update_one(
                {"_id": current["_id"], "version": payload.version, "is_deleted": False},
                {
                    "$set": {
                        "is_deleted": True,
                        "deleted_by": actor.require_id(),
                        "deleted_at": now,
                    },
                    "$inc": {"version": 1},
                    "$push": {"history": event},
                },
            )
            if not result.modified_count:
                raise ConflictError("This row changed. Reload before deleting.")
    return {"deleted": True, "id": record_id}


async def lookups(
    service: "DailyOperationsService", actor: User, search: str = ""
) -> dict[str, Any]:
    await service.authorize(actor, "follow-ups")
    own_id = await service.employee_id(actor)
    employees_query: dict[str, Any] = {"is_deleted": False, "status": "active"}
    if actor.role != OWNER:
        employees_query["_id"] = ObjectId(own_id)
    employees = (
        await service.db.employees.find(employees_query, {"display_name": 1})
        .sort("display_name", 1)
        .limit(100)
        .to_list(100)
    )
    own_profile = (
        await service.db.owner_profiles.find_one(
            {"user_id": actor.require_id(), "is_deleted": False}, {"full_name": 1}
        )
        if actor.role == OWNER
        else None
    )
    self_name = next(
        (e["display_name"] for e in employees if str(e["_id"]) == own_id),
        (own_profile or {}).get("full_name", "Owner" if actor.role == OWNER else ""),
    )
    query: dict[str, Any] = {"is_deleted": False, "product_category": "loan"}
    if actor.role != OWNER:
        query["assigned_to"] = own_id
    if search:
        query["full_name"] = {"$regex": re.escape(search), "$options": "i"}
    leads = (
        await service.db.leads.find(
            query, {"full_name": 1, "mobile": 1, "lead_code": 1, "product_id": 1}
        )
        .sort("created_at", -1)
        .limit(50)
        .to_list(50)
    )
    cases_query: dict[str, Any] = {"is_deleted": False, "case_type": "loan"}
    if actor.role != OWNER:
        cases_query.update(assigned_to=own_id, moved_to_loan_management_at={"$ne": None})
    if search:
        matching_customers = (
            await service.db.customers.find(
                {"is_deleted": False, "full_name": {"$regex": re.escape(search), "$options": "i"}},
                {"_id": 1},
            )
            .limit(100)
            .to_list(100)
        )
        cases_query["$or"] = [
            {"case_code": {"$regex": re.escape(search), "$options": "i"}},
            {"customer_id": {"$in": [str(c["_id"]) for c in matching_customers]}},
        ]
    cases = (
        await service.db.application_workflows.find(
            cases_query,
            {
                "case_code": 1,
                "customer_id": 1,
                "current_status": 1,
                "loan_details.bank_nbfc_name": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(50)
        .to_list(50)
    )
    customer_ids = [ObjectId(c["customer_id"]) for c in cases if c.get("customer_id")]
    customers = {
        str(c["_id"]): c
        for c in await service.db.customers.find(
            {"_id": {"$in": customer_ids}, "is_deleted": False}, {"full_name": 1, "mobile": 1}
        ).to_list(50)
    }
    return {
        "self_id": own_id,
        "self_name": self_name,
        "employees": [{"id": str(e["_id"]), "name": e["display_name"]} for e in employees],
        "leads": [
            {
                "id": str(lead["_id"]),
                "name": lead["full_name"],
                "number": lead["mobile"],
                "code": lead.get("lead_code", ""),
            }
            for lead in leads
        ],
        "cases": [
            {
                "id": str(c["_id"]),
                "name": customers.get(c.get("customer_id"), {}).get("full_name", ""),
                "number": customers.get(c.get("customer_id"), {}).get("mobile", ""),
                "code": c.get("case_code", ""),
                "bank": (c.get("loan_details") or {}).get("bank_nbfc_name", ""),
                "status": c.get("current_status", ""),
            }
            for c in cases
        ],
    }
