"""Shared record and employee eligibility; uses the existing effective RBAC engine."""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.leads.constants import PRODUCT_CATEGORY_MODULE


def intake_filter(collection: str) -> dict[str, Any]:
    return {
        "is_deleted": False,
        **(
            {"stage": {"$in": ["fresh", "document_collection"]}}
            if collection == "leads"
            else {"status": {"$in": ["draft", "submitted"]}}
        ),
    }


async def eligible_record(
    db: AsyncIOMotorDatabase[Any], collection: str, row: dict[str, Any]
) -> bool:
    if row.get("is_deleted") or row.get("status") in {"rejected", "cancelled", "disbursed"}:
        return False
    if collection == "leads":
        return row.get("stage") in {"fresh", "document_collection"}
    if row.get("status") not in {"draft", "submitted"}:
        return False
    case = await db.application_workflows.find_one(
        {"application_id": str(row["_id"])},
        {"current_status": 1, "moved_to_loan_management_at": 1, "is_deleted": 1},
    )
    if case and (
        case.get("is_deleted") or case.get("moved_to_loan_management_at")
        or case.get("current_status") in {"rejected", "cancelled", "disbursed", "policy_issued"}
    ):
        return False
    if row.get("lead_id"):
        if not ObjectId.is_valid(row["lead_id"]):
            return False
        lead = await db.leads.find_one(
            {"_id": ObjectId(row["lead_id"]), "is_deleted": False}, {"stage": 1}
        )
        if not lead or lead.get("stage") in {"rejected", "loan_management"}:
            return False
    return True


async def eligible_employees(
    db: AsyncIOMotorDatabase[Any], ids: list[str], row: dict[str, Any], collection: str
) -> list[str]:
    employees = await db.employees.find(
        {
            "_id": {"$in": [ObjectId(e) for e in ids if ObjectId.is_valid(e)]},
            "status": "active",
            "is_deleted": False,
        }
    ).to_list(max(1, len(ids)))
    users = {
        str(u["_id"]): User.model_validate(u)
        async for u in db.users.find(
            {
                "_id": {"$in": [ObjectId(e["user_id"]) for e in employees]},
                "role": "employee",
                "status": "active",
                "is_deleted": False,
            }
        )
    }
    by_id = {str(e["_id"]): e for e in employees}
    engine = PermissionEngine(db)
    lead_resource = "leads"
    stage = row.get("stage", "fresh") if collection == "leads" else "document_collection"
    child = await db.permissions.find_one({"module": "leads", "resource": f"leads.{stage}", "is_deleted": False}, {"actions": 1})
    if child and "view" in child.get("actions", []):
        lead_resource = f"leads.{stage}"
    allowed = []
    module = PRODUCT_CATEGORY_MODULE.get(row.get("product_category", ""))
    if not module:
        return []
    for eid in ids:
        employee = by_id.get(eid)
        user = users.get(employee["user_id"]) if employee else None
        if not user:
            continue
        scope = {"branch_id": row.get("branch_id"), "department_id": row.get("department_id")}
        if not await engine.has_permission(
            user, module=module, resource="applications", action="view", **scope
        ):
            continue
        if not await engine.has_permission(
            user, module="leads", resource=lead_resource, action="view", **scope
        ):
            continue
        if collection == "applications" and not await engine.has_permission(
            user, module="customer", resource="customers", action="view", **scope
        ):
            continue
        allowed.append(eid)
    return allowed
