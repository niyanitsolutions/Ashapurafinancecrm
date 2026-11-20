from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ValidationError
from app.core.response import ApiResponse
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.leads.assignment_policy import eligible_employees, eligible_record
from app.features.leads.auto_assignment import owner_only
from app.features.leads.bulk_assignment import (
    BulkRequest,
    RetryRequest,
    authorize,
    execute,
    record_list,
    resolve,
)

lead_router = APIRouter()
application_router = APIRouter()
Actor = Annotated[User, Depends(get_current_active_user)]
Db = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]


@lead_router.post("/bulk-assign")
async def bulk_leads(payload: BulkRequest, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    if not payload.employee_id:
        raise ValidationError("Choose an employee.")
    return ApiResponse[dict[str, Any]].ok(
        await execute(
            db,
            actor,
            record_list("leads", payload.ids),
            payload.employee_id.lower(),
            payload.allow_reassignment,
            "bulk",
            payload.preview_id,
        )
    )


@application_router.post("/applications/bulk-assign")
async def bulk_applications(
    payload: BulkRequest, actor: Actor, db: Db
) -> ApiResponse[dict[str, Any]]:
    if not payload.employee_id:
        raise ValidationError("Choose an employee.")
    return ApiResponse[dict[str, Any]].ok(
        await execute(
            db,
            actor,
            record_list("applications", payload.ids),
            payload.employee_id.lower(),
            payload.allow_reassignment,
            "bulk",
            payload.preview_id,
        )
    )


@lead_router.post("/bulk-assignees")
async def assignees(
    payload: BulkRequest,
    actor: Actor,
    db: Db,
    collection: Literal["leads", "applications"] = "leads",
) -> ApiResponse[list[dict[str, Any]]]:
    await authorize(db, actor, collection)
    employees = (
        await db.employees.find({"status": "active", "is_deleted": False}, {"display_name": 1})
        .sort("display_name", 1)
        .limit(1000)
        .to_list(1000)
    )
    available = [str(e["_id"]) for e in employees]
    checked = set()
    for record in record_list(collection, payload.ids):
        row = await resolve(db, actor, collection, record["id"])
        if row and await eligible_record(db, collection, row):
            context = (row.get("product_category"), row.get("branch_id"), row.get("department_id"))
            if context not in checked:
                available = await eligible_employees(db, available, row, collection)
                checked.add(context)
    if not checked:
        return ApiResponse[list[dict[str, Any]]].ok([])
    return ApiResponse[list[dict[str, Any]]].ok(
        [
            {"id": str(e["_id"]), "name": e["display_name"]}
            for e in employees
            if str(e["_id"]) in available
        ]
    )


@lead_router.post("/auto-assignment/bulk-retry")
async def bulk_retry(payload: RetryRequest, actor: Actor, db: Db) -> ApiResponse[dict[str, Any]]:
    owner_only(actor)
    if any(
        set(r) != {"collection", "id"} or r.get("collection") not in {"leads", "applications"}
        for r in payload.records
    ):
        raise ValidationError("Choose valid Lead or Application references.")
    records = list(
        {
            (r["collection"], r["id"].lower()): {
                "collection": r["collection"],
                "id": r["id"].lower(),
            }
            for r in payload.records
        }.values()
    )
    return ApiResponse[dict[str, Any]].ok(
        await execute(db, actor, records, None, False, "retry", payload.preview_id)
    )
