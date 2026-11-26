"""Read-only, permission-scoped choices for the existing linked-workspace API."""

import re
from typing import Any

from bson import ObjectId

from app.constants.roles import OWNER
from app.features.access_control.permission_engine import PermissionEngine
from app.features.customer.identity_name import batch_application_names
from app.features.daily_operations.service import DailyOperationsService
from app.shared.customer_identity import mobile_match_pattern, normalize_mobile


async def search(service: DailyOperationsService, actor: Any, query: str) -> dict[str, Any]:
    await service.authorize(actor, "follow-ups", "create")
    await service.authorize_lead_view(actor)
    query = query.strip()
    if len(query) < 2:
        return {"items": [], "has_more": False}
    regex = {"$regex": re.escape(query), "$options": "i"}
    mobile: Any = regex
    try:
        mobile = {"$regex": mobile_match_pattern(normalize_mobile(query))}
    except ValueError:
        pass
    db = service.db
    own = await service.employee_id(actor)
    scope = {} if actor.role == OWNER else {"assigned_to": own}
    can_customer = await PermissionEngine(db).has_permission(
        actor, module="customer", resource="customers", action="view"
    )
    customers = (
        await db.customers.find(
            {
                "is_deleted": False,
                "$or": [
                    {"full_name": regex},
                    {"mobile": mobile},
                    {"customer_code": regex},
                ],
            },
            {"full_name": 1, "mobile": 1, "customer_code": 1, "user_id": 1},
        )
        .limit(51)
        .to_list(51)
        if can_customer
        else []
    )
    customer_map = {str(c["_id"]): c for c in customers}
    leads = (
        await db.leads.find(
            {
                "is_deleted": False,
                **scope,
                "$or": [
                    {"full_name": regex},
                    {"mobile": mobile},
                    {"lead_code": regex},
                ],
            }
        )
        .limit(51)
        .to_list(51)
    )
    apps = (
        await db.applications.find(
            {
                "is_deleted": False,
                **scope,
                "$or": [
                    {"application_code": regex},
                    {"customer_id": {"$in": list(customer_map)}},
                    {"lead_id": {"$in": [str(l["_id"]) for l in leads]}},
                ],
            }
        )
        .limit(51)
        .to_list(51)
        if can_customer
        else []
    )
    names = await batch_application_names(db, [str(a["_id"]) for a in apps])
    items = []
    for entity, rows in (("application", apps[:50]), ("lead", leads[:50])):
        for row in rows:
            rid = str(row["_id"])
            if entity == "lead" and await db.applications.find_one(
                {"lead_id": rid, "is_deleted": False}, {"_id": 1}
            ):
                continue  # Applications are separate explicit choices, never a first-match shortcut.
            customer = customer_map.get(row.get("customer_id", ""))
            if not customer and ObjectId.is_valid(row.get("customer_id")):
                customer = await db.customers.find_one(
                    {"_id": ObjectId(row["customer_id"]), "is_deleted": False},
                    {"full_name": 1, "mobile": 1, "customer_code": 1, "user_id": 1},
                )
            broken = bool(
                row.get("customer_id")
                and (
                    not customer
                    or (row.get("user_id") and row["user_id"] != customer.get("user_id"))
                )
            )
            if broken and actor.role != OWNER:
                continue
            employee = (
                await db.employees.find_one(
                    {"_id": ObjectId(row["assigned_to"])}, {"display_name": 1}
                )
                if ObjectId.is_valid(row.get("assigned_to"))
                else None
            )
            product = (
                await db[
                    "loan_products"
                    if row.get("product_category") == "loan"
                    else "insurance_products"
                ].find_one({"_id": ObjectId(row["product_id"])}, {"name": 1})
                if ObjectId.is_valid(row.get("product_id"))
                else None
            )
            workspaces = (
                await db.daily_follow_ups.find(
                    {f"{entity}_id": rid}, {"is_deleted": 1, "working_key": 1}
                )
                .limit(2)
                .to_list(2)
            )
            items.append(
                {
                    "entity": entity,
                    "id": rid,
                    "code": row.get(f"{entity}_code", rid),
                    "customer_name": "Identity requires Owner review"
                    if broken
                    else names.get(rid, "")
                    if entity == "application"
                    else row.get("full_name", ""),
                    "mobile": "" if broken else (customer or row).get("mobile", ""),
                    "customer_code": None if broken else (customer or {}).get("customer_code"),
                    "product": (product or {}).get("name", ""),
                    "status": row.get("status", ""),
                    "assigned_to_name": (employee or {}).get("display_name", "Unassigned"),
                    "workspace_status": "Owner review required"
                    if broken
                    or len(workspaces) > 1
                    or any(w.get("is_deleted") or not w.get("working_key") for w in workspaces)
                    else "Existing workspace"
                    if workspaces
                    else "Open linked workspace",
                }
            )
    # Customer-only choices never fabricate an application; review uses existing Owner tooling.
    if actor.role == OWNER:
        for cid, customer in customer_map.items():
            if not await db.applications.find_one(
                {"customer_id": cid, "is_deleted": False}, {"_id": 1}
            ):
                items.append(
                    {
                        "entity": "customer",
                        "id": cid,
                        "code": customer.get("customer_code", cid),
                        "customer_name": customer.get("full_name", ""),
                        "mobile": customer.get("mobile", ""),
                        "workspace_status": "No application — Owner identity review",
                    }
                )
    return {"items": items, "has_more": any(len(rows) > 50 for rows in (customers, apps, leads))}
