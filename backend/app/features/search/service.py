"""Bounded staff search over existing entities, scoped before projection."""

import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import EMPLOYEE, OWNER
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.customer.identity_name import mongo_application_name
from app.features.leads.document_collection import lookup
from app.features.leads.service import LeadService
from app.shared.customer_identity import mobile_match_pattern, normalize_mobile


async def search_records(
    db: AsyncIOMotorDatabase[Any], actor: User, query: str, page: int = 1
) -> list[dict[str, Any]]:
    if actor.role not in {OWNER, EMPLOYEE}:
        return []
    query = query.strip()
    if len(query) < 2 or len(query) > 120:
        return []
    regex = {"$regex": re.escape(query), "$options": "i"}
    mobile_regex = regex
    mobile_query: str | None = None
    try:
        mobile_query = normalize_mobile(query)
        mobile_regex = {"$regex": mobile_match_pattern(mobile_query), "$options": "i"}
    except ValueError:
        pass  # Non-phone text keeps the existing partial/name/code search behavior.
    from datetime import UTC, datetime

    from app.features.leads.document_collection import date_range

    calendar_bounds = None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            day = datetime.strptime(query, pattern).replace(tzinfo=UTC).date()
            calendar_bounds = date_range(day, day)
            break
        except ValueError:
            continue

    engine = PermissionEngine(db)
    employee = (
        await db.employees.find_one({"user_id": actor.require_id(), "is_deleted": False})
        if actor.role != OWNER
        else None
    )
    own = str(employee["_id"]) if employee else "no-assignment"
    offset = (page - 1) * 10
    results: list[dict[str, Any]] = []
    if await engine.has_permission(actor, module="customer", resource="customers", action="view"):
        customer_query: dict[str, Any] = {
            "is_deleted": False,
            "$or": [
                {key: mobile_regex if key == "mobile" else regex}
                for key in ["customer_code", "full_name", "mobile", "email"]
            ],
        }
        if actor.role == OWNER and re.fullmatch(r"[A-Za-z]{5}[0-9]{4}[A-Za-z]", query):
            from app.shared.customer_identity import pan_search_digest

            customer_query["$or"].append({"pan_search_digest": pan_search_digest(query)})
        if calendar_bounds:
            customer_query["$or"].append({"created_at": calendar_bounds})
        customer_pipeline: list[dict[str, Any]] = [{"$match": customer_query}]
        if actor.role != OWNER:
            customer_pipeline += [
                {"$set": {"cid": {"$toString": "$_id"}}},
                {
                    "$lookup": {
                        "from": "applications",
                        "let": {"cid": "$cid", "uid": "$user_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "is_deleted": False,
                                    "assigned_to": own,
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$customer_id", "$$cid"]},
                                            {"$eq": ["$user_id", "$$uid"]},
                                        ]
                                    },
                                }
                            },
                            {"$limit": 1},
                            {"$project": {"_id": 1}},
                        ],
                        "as": "permitted",
                    }
                },
                {"$match": {"permitted.0": {"$exists": True}}},
            ]
        customer_pipeline += [
            {"$sort": {"_id": -1}},
            {"$skip": offset},
            {"$limit": 10},
            {
                "$project": {
                    "_id": 0,
                    "type": {"$literal": "customer"},
                    "id": {"$toString": "$_id"},
                    "label": "$full_name",
                    "subtitle": "$customer_code",
                    "customer_code": "$customer_code",
                    "mobile": "$mobile",
                    "route": {
                        "$concat": [
                            "/customers/",
                            {"$toString": "$_id"},
                        ]
                    },
                }
            },
        ]
        direct_customers = await db.customers.aggregate(customer_pipeline).to_list(10)
        results.extend(direct_customers)

        match: dict[str, Any] = {"is_deleted": False}
        if actor.role != OWNER:
            match["assigned_to"] = own
        p: list[dict[str, Any]] = [{"$match": match}]
        p += lookup("customers", "customer_id", "customer")
        p += [
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$user_id", "$customer.user_id"]},
                            {"$ne": ["$customer.is_deleted", True]},
                        ]
                    }
                }
            }
        ]
        p += lookup("application_form_definitions", "form_definition_id", "schema")
        p += [{"$set": {"name": mongo_application_name()}}]
        p += lookup("employees", "assigned_to", "employee")
        p += lookup("loan_products", "product_id", "loan")
        p += lookup("insurance_products", "product_id", "insurance")
        p += lookup("branches", "employee.branch_id", "branch")
        p += lookup("leads", "lead_id", "lead")
        p += [
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "assigned_by",
                    "foreignField": "user_id",
                    "as": "assigner",
                }
            }
        ]

        p += [
            {
                "$match": {
                    "$or": [
                        {key: mobile_regex if key.endswith("mobile") else regex}
                        for key in [
                            "application_code",
                            "lead.lead_code",
                            "assigner.display_name",
                            "branch.name",
                            "customer.customer_code",
                            "customer.full_name",
                            "name",
                            "customer.mobile",
                            "customer.email",
                            "employee.display_name",
                            "loan.name",
                            "insurance.name",
                            "status",
                        ]
                    ]
                }
            }
        ]
        if calendar_bounds:
            p[-1]["$match"]["$or"].extend(
                [{field: calendar_bounds} for field in ("created_at", "assigned_at")]
            )
        if actor.role == OWNER and re.fullmatch(r"[A-Za-z]{5}[0-9]{4}[A-Za-z]", query):
            from app.shared.customer_identity import pan_search_digest

            p[-1]["$match"]["$or"].append({"customer.pan_search_digest": pan_search_digest(query)})
        facets = {
            "applications": [
                {"$sort": {"created_at": -1, "_id": -1}},
                {"$skip": offset},
                {"$limit": 10},
                {
                    "$project": {
                        "_id": 0,
                        "type": {"$literal": "application"},
                        "id": {"$toString": "$_id"},
                        "label": "$application_code",
                        "subtitle": {
                            "$concat": [
                                "$name",
                                " | ",
                                "$customer.customer_code",
                                " | ",
                                {"$ifNull": ["$loan.name", {"$ifNull": ["$insurance.name", ""]}]},
                                " | ",
                                "$status",
                                " | ",
                                {"$ifNull": ["$employee.display_name", "Unassigned"]},
                            ]
                        },
                        "customer_name": "$name",
                        "product_name": {"$ifNull": ["$loan.name", "$insurance.name"]},
                        "status": "$status",
                        "assigned_to_name": "$employee.display_name",
                        "route": {
                            "$concat": [
                                "/applications/",
                                {"$toString": "$_id"},
                                "?from=document-collection",
                            ]
                        },
                    }
                },
            ],
            "customers": [
                {
                    "$group": {
                        "_id": "$customer._id",
                        "label": {"$first": "$name"},
                        "subtitle": {"$first": "$customer.customer_code"},
                        "customer_code": {"$first": "$customer.customer_code"},
                        "mobile": {"$first": "$customer.mobile"},
                    }
                },
                {"$sort": {"_id": -1}},
                {"$skip": offset},
                {"$limit": 10},
                {
                    "$project": {
                        "_id": 0,
                        "type": {"$literal": "customer"},
                        "id": {"$toString": "$_id"},
                        "label": 1,
                        "subtitle": 1,
                        "customer_code": 1,
                        "mobile": 1,
                        "route": {
                            "$concat": [
                                "/customers/",
                                {"$toString": "$_id"},
                            ]
                        },
                    }
                },
            ],
        }
        data = await db.applications.aggregate(p + [{"$facet": facets}]).to_list(1)
        if data:
            results.extend(data[0]["customers"] + data[0]["applications"])
    if await engine.has_permission(actor, module="leads", resource="leads", action="view"):
        service = LeadService(db)
        leads, _ = await service.list_leads(
            search=mobile_query or query,
            source_id=None,
            product_category=None,
            product_id=None,
            assigned_to=None,
            status=None,
            skip=offset,
            limit=10,
            sort=[("created_at", -1), ("_id", -1)],
            actor=actor,
        )
        results.extend(
            {
                "type": "lead",
                "id": lead.require_id(),
                "label": lead.lead_code,
                "subtitle": " | ".join(filter(None, [lead.full_name, lead.mobile, lead.status])),
                "mobile": lead.mobile,
                "status": lead.status,
                "route": "/leads/" + lead.require_id(),
            }
            for lead in leads
        )
    # The employee detail API is Owner-only, so search must not widen its boundary.
    if actor.role == OWNER:
        rows = (
            await db.employees.find(
                {
                    "is_deleted": False,
                    "$or": [
                        {key: mobile_regex if key == "mobile" else regex}
                        for key in ["display_name", "employee_code", "mobile"]
                    ],
                },
                {"display_name": 1, "employee_code": 1, "designation_id": 1},
            )
            .sort([("_id", -1)])
            .skip(offset)
            .limit(10)
            .to_list(10)
        )
        from bson import ObjectId

        designation_ids = {
            row.get("designation_id")
            for row in rows
            if ObjectId.is_valid(row.get("designation_id"))
        }
        designations = {
            str(d["_id"]): d["name"]
            async for d in db.designations.find(
                {
                    "_id": {"$in": [ObjectId(value) for value in designation_ids]},
                    "is_deleted": False,
                },
                {"name": 1},
            )
        }
        results.extend(
            {
                "type": "employee",
                "id": str(row["_id"]),
                "label": row.get("display_name", "Employee"),
                "subtitle": row.get("employee_code"),
                "employee_code": row.get("employee_code"),
                "designation": designations.get(row.get("designation_id")),
                "route": "/employees/" + str(row["_id"]),
            }
            for row in rows
        )
    seen: set[tuple[str, str]] = set()
    unique = []
    for row in results:
        identity = (row["type"], row["id"])
        if identity not in seen:
            seen.add(identity)
            unique.append(row)
    for row in results:
        if row["type"] == "customer" and row.get("label") not in {
            "Customer",
            "Name unavailable",
            None,
        }:
            for item in unique:
                if item["type"] == "customer" and item["id"] == row["id"]:
                    item["label"] = row["label"]
    from app.features.customer.identity_name import actual_name

    for result in unique:
        if result["type"] == "customer":
            result["label"] = actual_name(result.get("label")) or "Name unavailable"
        elif result["type"] == "application":
            result["label"] = result.get("label") or "Application code unavailable"
    return sorted(unique, key=lambda row: row["type"])
