"""Read-only operational metrics. Financial totals come only from persisted loan cases."""

from typing import Any

from app.features.access_control.permission_engine import PermissionEngine
from app.features.daily_operations.follow_status import status_stage
from app.features.daily_operations.handover import employee_id, queue
from app.utils.datetime import to_ist, utc_now


async def summary(db: Any, actor: Any, filters: Any) -> dict[str, Any]:
    own = await employee_id(db, actor)
    scope = {"is_deleted": False, **({"assigned_to": own} if actor.role != "owner" else {})}
    engine = PermissionEngine(db)
    result: dict[str, Any] = {}
    daily_pipeline: list[dict[str, Any]] = []
    financial_pipeline: list[dict[str, Any]] = []
    from datetime import timedelta

    common = {
        "date_from": to_ist(filters.start).date().isoformat(),
        "date_to": to_ist(filters.end - timedelta(microseconds=1)).date().isoformat(),
    }
    if await engine.has_permission(
        actor, module="daily_operations", resource="follow-ups", action="view"
    ):
        match = {**scope, "date": {"$gte": filters.start, "$lt": filters.end}}
        pipeline = [{"$match": match}, status_stage(utc_now())]
        if filters.product_category or filters.source_id:
            pipeline += [
                {
                    "$lookup": {
                        "from": "applications",
                        "localField": "application_oid",
                        "foreignField": "_id",
                        "as": "application",
                    }
                },
                {
                    "$match": {
                        **(
                            {"application.product_category": filters.product_category}
                            if filters.product_category
                            else {}
                        ),
                        **(
                            {"application.source_id": filters.source_id}
                            if filters.source_id
                            else {}
                        ),
                    }
                },
            ]
        daily_pipeline = list(pipeline)
        rows = await db.daily_follow_ups.aggregate(
            pipeline
            + [
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": 1},
                        "pending": {
                            "$sum": {"$cond": [{"$eq": ["$status", "FOLLOW UP PENDING"]}, 1, 0]}
                        },
                        "completed": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$status", ["DISBURSE", "REJECTED WITH REASON"]]},
                                    1,
                                    0,
                                ]
                            }
                        },
                    }
                }
            ]
        ).to_list(1)
        counts = rows[0] if rows else {}
        result.update(
            followups=counts.get("total", 0),
            pending=counts.get("pending", 0),
            completed=counts.get("completed", 0),
        )
    if await engine.has_permission(
        actor, module="loan_management", resource="applications", action="view"
    ) or await engine.has_permission(
        actor, module="loan_management", resource="applications.disbursed", action="view"
    ):
        match = {
            **scope,
            "case_type": "loan",
            "current_status": "disbursed",
            "loan_details.disbursed_at": {"$gte": filters.start, "$lt": filters.end},
            "loan_details.disbursed_amount": {"$gt": 0},
        }
        if filters.product_category and filters.product_category != "loan":
            match["case_type"] = "never_matches"
        pipeline = [{"$match": match}]
        if filters.source_id:
            pipeline += [
                {
                    "$lookup": {
                        "from": "applications",
                        "let": {"aid": "$application_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {"$eq": [{"$toString": "$_id"}, "$$aid"]},
                                    "source_id": filters.source_id,
                                }
                            }
                        ],
                        "as": "source",
                    }
                },
                {"$match": {"source.0": {"$exists": True}}},
            ]
        financial_pipeline = list(pipeline)
        rows = await db.application_workflows.aggregate(
            pipeline
            + [
                {
                    "$group": {
                        "_id": None,
                        "cases": {"$sum": 1},
                        "approved": {"$sum": {"$ifNull": ["$loan_details.offered_amount", 0]}},
                        "disbursed": {"$sum": "$loan_details.disbursed_amount"},
                        "topups": {
                            "$sum": {
                                "$cond": [
                                    {
                                        "$in": [
                                            "$loan_details.top_up_period",
                                            ["3_months", "6_months", "12_months", "custom"],
                                        ]
                                    },
                                    1,
                                    0,
                                ]
                            }
                        },
                    }
                }
            ]
        ).to_list(1)
        values = rows[0] if rows else {}
        result.update(
            disbursed_cases=values.get("cases", 0),
            approved_amount=round(values.get("approved", 0), 2),
            disbursed_amount=round(values.get("disbursed", 0), 2),
            topups=values.get("topups", 0),
        )
    # Count distinct visible transferred records, never the number of historical hops.
    transfers = await queue(
        db,
        actor,
        date_from=to_ist(filters.start).date(),
        date_to=to_ist(filters.end - timedelta(microseconds=1)).date(),
    )
    result["transfers"] = transfers["total"]
    employees = []
    if actor.role == "owner":
        workload = {}
        if daily_pipeline:
            async for row in db.daily_follow_ups.aggregate(
                daily_pipeline
                + [
                    {"$group": {"_id": "$assigned_to", "followups": {"$sum": 1}}},
                    {"$sort": {"followups": -1, "_id": 1}},
                    {"$limit": 20},
                ]
            ):
                workload[row["_id"]] = {
                    "employee_id": row["_id"],
                    "followups": row["followups"],
                    "disbursed_cases": 0,
                    "disbursed_amount": 0,
                }
        if financial_pipeline:
            async for row in db.application_workflows.aggregate(
                financial_pipeline
                + [
                    {
                        "$group": {
                            "_id": "$assigned_to",
                            "cases": {"$sum": 1},
                            "amount": {"$sum": "$loan_details.disbursed_amount"},
                        }
                    },
                    {"$sort": {"amount": -1, "_id": 1}},
                    {"$limit": 20},
                ]
            ):
                item = workload.setdefault(row["_id"], {"employee_id": row["_id"], "followups": 0})
                item.update(disbursed_cases=row["cases"], disbursed_amount=round(row["amount"], 2))
        from bson import ObjectId

        ids = [ObjectId(i) for i in workload if ObjectId.is_valid(i)]
        names = (
            {
                str(e["_id"]): e["display_name"]
                async for e in db.employees.find({"_id": {"$in": ids}}, {"display_name": 1})
            }
            if ids
            else {}
        )
        employees = [
            {**r, "employee": names.get(eid, "Owner / unassigned")} for eid, r in workload.items()
        ]
    return {
        "employee_summary": employees,
        "metrics": result,
        "date_bounds": common,
        "definition": "Follow-ups use activity DATE. Financial totals count each persisted disbursed Loan case once using disbursement date; approved total is approval on those same disbursed cases. Transfer totals count distinct visible sent/received records in the transfer period.",
    }
