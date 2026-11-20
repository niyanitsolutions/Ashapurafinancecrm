"""Owner-only controls; mounted ahead of dynamic lead-id routes."""

from typing import Annotated, Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import NotFoundError
from app.core.response import ApiResponse
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.leads.assignment_policy import intake_filter
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment, owner_only

router = APIRouter(prefix="/auto-assignment", tags=["auto-assignment"])
Db = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
Actor = Annotated[User, Depends(get_current_active_user)]


@router.get("")
async def settings(db: Db, actor: Actor) -> ApiResponse[dict[str, Any]]:
    owner_only(actor)
    service = AutoAssignment(db)
    rows = (
        await db.employees.find({"is_deleted": False}, {"display_name": 1})
        .sort("display_name", 1)
        .limit(1000)
        .to_list(1000)
    )
    active = set(await service.active_pool([str(e["_id"]) for e in rows]))
    counts = {
        r["_id"]: r["count"]
        async for r in db.leads.aggregate(
            [
                {
                    "$match": {
                        "is_deleted": False,
                        "assigned_to": {"$in": [str(e["_id"]) for e in rows]},
                    }
                },
                {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}},
            ]
        )
    }
    employees = [
        {
            "id": str(e["_id"]),
            "name": e["display_name"],
            "active": str(e["_id"]) in active,
            "assigned_leads": counts.get(str(e["_id"]), 0),
        }
        for e in rows
    ]
    return ApiResponse[dict[str, Any]].ok({**await service.settings(), "employees": employees})


@router.put("")
async def save_settings(
    payload: AssignmentSettings, db: Db, actor: Actor
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse[dict[str, Any]].ok(await AutoAssignment(db).save(payload, actor))


@router.get("/pending")
async def pending(
    db: Db, actor: Actor, page: Annotated[int, Query(ge=1)] = 1
) -> ApiResponse[dict[str, Any]]:
    owner_only(actor)
    items = []
    total = 0
    for name in ("leads", "applications"):
        query = {**intake_filter(name), "assigned_to": None}
        total += await db[name].count_documents(query)
        # Combined page built server-side using unionWith below in real Mongo.
    pipeline: list[dict[str, Any]] = [
        {"$match": {**intake_filter("leads"), "assigned_to": None}},
        {"$project": {"created_at": 1, "assignment_error": 1, "collection": {"$literal": "leads"}}},
        {
            "$unionWith": {
                "coll": "applications",
                "pipeline": [
                    {
                        "$match": {**intake_filter("applications"), "assigned_to": None}
                    },
                    {
                        "$project": {
                            "created_at": 1,
                            "assignment_error": 1,
                            "collection": {"$literal": "applications"},
                        }
                    },
                ],
            }
        },
        {"$sort": {"created_at": 1, "_id": 1}},
        {"$skip": (page - 1) * 20},
        {"$limit": 20},
    ]
    async for row in db.leads.aggregate(pipeline):
        items.append(
            {
                "id": str(row["_id"]),
                "collection": row["collection"],
                "created_at": row["created_at"],
                "error": row.get("assignment_error"),
                "route": f"/leads/{row['_id']}"
                if row["collection"] == "leads"
                else f"/applications/{row['_id']}",
            }
        )
    return ApiResponse[dict[str, Any]].ok({"items": items, "total": total, "page": page})


@router.post("/retry/{collection}/{record_id}")
async def retry(
    collection: Literal["leads", "applications"], record_id: str, db: Db, actor: Actor
) -> ApiResponse[dict[str, Any]]:
    owner_only(actor)
    if not ObjectId.is_valid(record_id):
        raise NotFoundError("Record not found.")
    if not await db[collection].find_one(
        {"_id": ObjectId(record_id), "is_deleted": False}, {"_id": 1}
    ):
        raise NotFoundError("Record not found.")
    await AutoAssignment(db).assign(collection, record_id, actor, source="retry")
    row = await db[collection].find_one(
        {"_id": ObjectId(record_id)}, {"assigned_to": 1, "assignment_pending": 1}
    )
    return ApiResponse[dict[str, Any]].ok(
        {
            "assigned_to": (row or {}).get("assigned_to"),
            "pending": (row or {}).get("assignment_pending", False),
        }
    )


@router.get("/history")
async def history(
    db: Db, actor: Actor, page: Annotated[int, Query(ge=1)] = 1
) -> ApiResponse[dict[str, Any]]:
    owner_only(actor)
    query = {
        "event_type": {
            "$in": ["crm_auto_assigned", "crm_bulk_assigned", "lead_assigned", "lead_unassigned", "application_assigned"]
        }
    }
    rows = (
        await db.audit_logs.find(
            query, {"event_type": 1, "user_id": 1, "metadata": 1, "created_at": 1}
        )
        .sort("created_at", -1)
        .skip((page - 1) * 20)
        .limit(20)
        .to_list(20)
    )
    employee_ids = {(r.get("metadata") or {}).get("employee_id") for r in rows}
    actor_ids = {r.get("user_id") for r in rows}
    employees = await db.employees.find(
        {
            "$or": [
                {"_id": {"$in": [ObjectId(eid) for eid in employee_ids if ObjectId.is_valid(eid)]}},
                {"user_id": {"$in": list(actor_ids)}},
            ]
        },
        {"user_id": 1, "display_name": 1},
    ).to_list(40)
    employee_names = {str(e["_id"]): e["display_name"] for e in employees}
    actor_names = {e["user_id"]: e["display_name"] for e in employees}
    actor_names.update(
        {
            o["user_id"]: o["full_name"]
            async for o in db.owner_profiles.find(
                {"user_id": {"$in": list(actor_ids)}}, {"user_id": 1, "full_name": 1}
            )
        }
    )
    allowed = {
        "employee_id",
        "old_employee_id",
        "record_id",
        "lead_id",
        "application_id",
        "collection",
        "source",
        "sequence",
    }
    return ApiResponse[dict[str, Any]].ok(
        {
            "items": [
                {
                    "id": str(r["_id"]),
                    "event_type": r["event_type"],
                    "created_at": r["created_at"],
                    "actor_name": actor_names.get(r.get("user_id") or "", "CRM user"),
                    "employee_name": employee_names.get(
                        (r.get("metadata") or {}).get("employee_id") or "", "Unassigned or Owner"
                    ),
                    "metadata": {
                        k: v for k, v in (r.get("metadata") or {}).items() if k in allowed
                    },
                }
                for r in rows
            ],
            "total": await db.audit_logs.count_documents(query),
        }
    )
