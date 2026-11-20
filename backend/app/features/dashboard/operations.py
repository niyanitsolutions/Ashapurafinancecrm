"""Additional operational monitoring; no lifecycle or financial calculations."""

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.dashboard.filters import DashboardFilters
from app.features.dashboard.widget_providers import _scope_to_employee
from app.features.leads.auto_assignment import AutoAssignment
from app.features.leads.constants import LeadStage
from app.features.leads.service import LeadService
from app.utils.datetime import end_of_day_ist, start_of_day_ist


async def operational_summary(
    db: AsyncIOMotorDatabase[Any],
    actor: User,
    filters: DashboardFilters,
    employee: str | None = None,
    stage: str | None = None,
    page: int = 1,
) -> dict[str, Any]:
    engine = PermissionEngine(db)
    if not await engine.has_permission(actor, module="leads", resource="leads", action="view"):
        raise ForbiddenError("Lead viewing permission is required for operational monitoring.")
    if stage and stage not in LeadStage.ALL:
        raise ValidationError("Choose an existing lead stage.")
    if employee and not ObjectId.is_valid(employee):
        raise ValidationError("Choose a valid employee.")
    employee_id = employee if actor.role == OWNER else await _scope_to_employee(db, actor)
    query: dict[str, Any] = {"is_deleted": False}
    if employee_id:
        query["assigned_to"] = employee_id
    if filters.product_category:
        query["product_category"] = filters.product_category
    if filters.source_id:
        query["source_id"] = filters.source_id
    if stage:
        query["stage"] = stage
    cohort = {**query, "created_at": {"$gte": filters.start, "$lt": filters.end}}
    grouped = await db.leads.aggregate(
        [
            {"$match": cohort},
            {
                "$group": {
                    "_id": {"employee": "$assigned_to", "stage": "$stage"},
                    "count": {"$sum": 1},
                }
            },
            {
                "$group": {
                    "_id": "$_id.employee",
                    "assigned": {"$sum": "$count"},
                    "stages": {"$push": {"stage": "$_id.stage", "count": "$count"}},
                }
            },
            {"$sort": {"assigned": -1, "_id": 1}},
            {
                "$facet": {
                    "items": [{"$skip": (page - 1) * 20}, {"$limit": 20}],
                    "total": [{"$count": "value"}],
                }
            },
        ]
    ).to_list(1)
    result = grouped[0] if grouped else {"items": [], "total": []}
    ids = [ObjectId(r["_id"]) for r in result["items"] if r["_id"] and ObjectId.is_valid(r["_id"])]
    names = {
        str(e["_id"]): e["display_name"]
        async for e in db.employees.find({"_id": {"$in": ids}}, {"display_name": 1})
    }
    workload = [
        {
            "employee_id": r["_id"],
            "employee": names.get(r["_id"], "Owner" if r["_id"] else "Unassigned"),
            "leads": r["assigned"],
            "stages": {s["stage"]: s["count"] for s in r["stages"]},
        }
        for r in result["items"]
    ]
    today, tomorrow = start_of_day_ist(), end_of_day_ist()
    followups = {
        "overdue": await db.leads.count_documents(
            {**query, "next_follow_up_date": {"$lt": today, "$ne": None}}
        ),
        "today": await db.leads.count_documents(
            {**query, "next_follow_up_date": {"$gte": today, "$lt": tomorrow}}
        ),
        "upcoming": await db.leads.count_documents(
            {**query, "next_follow_up_date": {"$gte": tomorrow}}
        ),
    }
    priorities = [
        {
            "id": str(r["_id"]),
            "name": r["full_name"],
            "reference": r["lead_code"],
            "due_at": r["next_follow_up_date"],
            "route": f"/leads/{r['_id']}",
        }
        async for r in db.leads.find(
            {**query, "next_follow_up_date": {"$lt": tomorrow, "$ne": None}},
            {"full_name": 1, "lead_code": 1, "next_follow_up_date": 1},
        )
        .sort("next_follow_up_date", 1)
        .limit(10)
    ]
    # Use the existing tab-count implementation, including the merged application rows
    # in Document Collection. These badges are current stock, not date-cohort counts.
    tabs = (await LeadService(db).get_tab_counts(actor)).model_dump()
    response: dict[str, Any] = {
        "tabs": tabs,
        "followups": followups,
        "priorities": priorities,
        "workload": workload,
        "workload_total": result["total"][0]["value"] if result["total"] else 0,
        "cohort_leads": await db.leads.count_documents(cohort),
        "page": page,
        "definition": "Workload counts leads created in the selected period. Follow-ups use current lead schedules. Tab badges use existing current tab rules.",
    }
    if await engine.has_permission(
        actor, module="daily_operations", resource="follow-ups", action="view"
    ):
        from app.features.daily_operations.service import DailyOperationsService

        daily = DailyOperationsService(db)
        all_daily = await daily.list_records(
            "follow-ups", actor, employee=employee_id or "", page_size=1
        )
        overdue_daily = await daily.list_records(
            "follow-ups",
            actor,
            employee=employee_id or "",
            overdue=True,
            sort="due_date",
            page_size=10,
        )
        response["daily_followups"] = {
            "total": all_daily["total"],
            "overdue": overdue_daily["total"],
            "priorities": [
                {
                    "id": r["id"],
                    "name": r["customer_name"],
                    "due_date": r.get("due_date"),
                    "route": f"/daily-operations/follow-ups?record={r['id']}",
                }
                for r in overdue_daily["items"]
            ],
        }
    if await engine.has_permission(actor, module="customer", resource="customers", action="view"):
        app_query: dict[str, Any] = {
            "is_deleted": False,
            "created_at": {"$gte": filters.start, "$lt": filters.end},
        }
        if employee_id:
            app_query["assigned_to"] = employee_id
        if filters.product_category:
            app_query["product_category"] = filters.product_category
        response["applications"] = {
            "submitted": await db.applications.count_documents(
                {**app_query, "status": "submitted"}
            ),
            "draft": await db.applications.count_documents({**app_query, "status": "draft"}),
        }
        recent = (
            await db.applications.find(
                {**app_query, "status": "submitted"},
                {"application_code": 1, "submitted_at": 1, "customer_id": 1},
            )
            .sort("submitted_at", -1)
            .limit(10)
            .to_list(10)
        )
        customer_names = {
            str(c["_id"]): c["full_name"]
            async for c in db.customers.find(
                {
                    "_id": {
                        "$in": [ObjectId(r["customer_id"]) for r in recent if r.get("customer_id")]
                    },
                    "is_deleted": False,
                },
                {"full_name": 1},
            )
        }
        response["recent_submissions"] = [
            {
                "id": str(r["_id"]),
                "reference": r["application_code"],
                "name": customer_names.get(r.get("customer_id"), "Name not provided"),
                "route": f"/applications/{r['_id']}",
                "submitted_at": r.get("submitted_at"),
            }
            for r in recent
        ]
    if actor.role == OWNER:
        response["assignment"] = {
            **await AutoAssignment(db).settings(),
            "pending": sum(
                [
                    await db[name].count_documents(
                        {"is_deleted": False, "assigned_to": None, "auto_assignment_eligible": True}
                    )
                    for name in ("leads", "applications")
                ]
            ),
            "failures": sum(
                [
                    await db[name].count_documents(
                        {"is_deleted": False, "assigned_to": None, "assignment_pending": True}
                    )
                    for name in ("leads", "applications")
                ]
            ),
            "total_assigned": await db.audit_logs.count_documents(
                {"event_type": "crm_auto_assigned"}
            ),
        }
    return response
