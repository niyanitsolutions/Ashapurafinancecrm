"""Customer-grouped, server-paginated Document Collection read model.

The pipeline scopes before joining, filters before grouping, and never repairs data.
"""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.config.database import get_database
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.customer.identity_name import mongo_application_name
from app.features.leads.constants import LeadStage
from app.features.leads.service import LeadService

router = APIRouter()
Db = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]
Actor = Annotated[User, require_permission("leads", "leads", "view")]


class CollectionFilters(BaseModel):
    search: str = Field(default="", max_length=120)
    customer_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{24}$")
    assigned_to: str | None = None
    assigned_by: str | None = None
    assigned_from: date | None = None
    assigned_until: date | None = None
    product_id: str | None = None
    product_category: str | None = None
    application_status: str | None = None
    created_from: date | None = None
    created_until: date | None = None
    source_id: str | None = None
    branch_id: str | None = None
    follow_up_from: date | None = None
    follow_up_until: date | None = None
    overdue: bool = False
    follow_up_status: str | None = None
    follow_up_employee: str | None = None
    document_status: str | None = None
    designation_id: str | None = None
    customer_status: str | None = None
    bank_id: str | None = None


def lookup(collection: str, local: str, alias: str) -> list[dict[str, Any]]:
    return [
        {
            "$set": {
                "_join": {
                    "$convert": {
                        "input": "$" + local,
                        "to": "objectId",
                        "onError": None,
                        "onNull": None,
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": collection,
                "localField": "_join",
                "foreignField": "_id",
                "as": alias,
            }
        },
        {"$set": {alias: {"$arrayElemAt": ["$" + alias, 0]}}},
    ]


def date_range(start: date | None, end: date | None) -> dict[str, datetime]:
    result = {}
    if start:
        result["$gte"] = datetime.combine(start, datetime.min.time(), UTC) - timedelta(
            hours=5, minutes=30
        )
    if end:
        result["$lt"] = datetime.combine(
            end + timedelta(days=1), datetime.min.time(), UTC
        ) - timedelta(hours=5, minutes=30)
    return result


async def pipeline(
    db: AsyncIOMotorDatabase[Any], actor: User, f: CollectionFilters
) -> list[dict[str, Any]]:
    assigned, _ = await LeadService(db)._scope_query(
        actor, f.assigned_to, LeadStage.DOCUMENT_COLLECTION
    )
    match: dict[str, Any] = {"is_deleted": False, "daily_followup_moved_at": None, "$or": [{"referral_attribution": None}, {"referral_attribution.submitted_to_afs_at": {"$ne": None}}], "status": {"$in": ["draft", "submitted"]}}
    if assigned:
        # Use the same actor-derived employee scope as the existing intake list.
        match["assigned_to"] = None if assigned == "__unassigned__" else assigned
    p: list[dict[str, Any]] = [{"$match": match}, {"$set": {"record_id": {"$toString": "$_id"}}}]
    lead_match = {"is_deleted": False, "stage": "document_collection"}
    if assigned:
        lead_match["assigned_to"] = None if assigned == "__unassigned__" else assigned
    p += [
        {
            "$unionWith": {
                "coll": "leads",
                "pipeline": [
                    {"$match": lead_match},
                    {"$set": {"record_id": {"$toString": "$_id"}}},
                    {
                        "$lookup": {
                            "from": "applications",
                            "let": {
                                "lid": "$record_id",
                                "cid": "$customer_id",
                                "pid": "$product_id",
                            },
                            "pipeline": [
                                {
                                    "$match": {
                                        "is_deleted": False,
                                        "$expr": {
                                            "$or": [
                                                {"$eq": ["$lead_id", "$$lid"]},
                                                {
                                                    "$and": [
                                                        {"$ne": ["$$cid", None]},
                                                        {"$eq": ["$customer_id", "$$cid"]},
                                                        {"$eq": ["$product_id", "$$pid"]},
                                                    ]
                                                },
                                            ]
                                        },
                                    }
                                },
                                {"$limit": 1},
                                {"$project": {"_id": 1}},
                            ],
                            "as": "linked_apps",
                        }
                    },
                    {"$match": {"linked_apps.0": {"$exists": False}}},
                    {
                        "$set": {
                            "lead_id": "$record_id",
                            "record_kind": "lead",
                            "application_code": "$lead_code",
                            "status": "draft",
                        }
                    },
                ],
            }
        }
    ]
    p += lookup("leads", "lead_id", "lead")
    p += [
        {
            "$lookup": {
                "from": "application_workflows",
                "localField": "record_id",
                "foreignField": "application_id",
                "as": "cases",
            }
        },
        {
            "$match": {
                "cases": {
                    "$not": {
                        "$elemMatch": {
                            "is_deleted": False,
                            "$or": [
                                {"moved_to_loan_management_at": {"$ne": None}},
                                {"case_type": "insurance", "current_status": {"$ne": "fresh_lead"}},
                            ],
                        }
                    }
                }
            }
        },
        {
            "$match": {
                "$or": [
                    {"lead_id": None},
                    {"lead.stage": "document_collection", "lead.is_deleted": False},
                ]
            }
        },
    ]
    p += lookup("customers", "customer_id", "customer")
    # A mismatched reference must not expose the other customer's contact/identity.
    p += [
        {
            "$set": {
                "customer": {
                    "$cond": [
                        {
                            "$and": [
                                {
                                    "$or": [
                                        {"$eq": ["$customer.user_id", "$user_id"]},
                                        {
                                            "$and": [
                                                {"$eq": ["$record_kind", "lead"]},
                                                {
                                                    "$eq": [
                                                        "$customer.converted_from_lead_id",
                                                        "$record_id",
                                                    ]
                                                },
                                            ]
                                        },
                                    ]
                                },
                                {"$ne": ["$customer.is_deleted", True]},
                            ]
                        },
                        "$customer",
                        None,
                    ]
                }
            }
        }
    ]
    p += lookup("employees", "assigned_to", "employee")
    p += lookup("loan_products", "product_id", "loan_product")
    p += lookup("insurance_products", "product_id", "insurance_product")
    p += [
        {
            "$lookup": {
                "from": "application_documents",
                "localField": "record_id",
                "foreignField": "application_id",
                "as": "documents",
            }
        },
        {
            "$lookup": {
                "from": "daily_follow_ups",
                "localField": "record_id",
                "foreignField": "application_id",
                "as": "followups",
            }
        },
        {
            "$set": {
                "documents": {
                    "$filter": {
                        "input": "$documents",
                        "as": "doc",
                        "cond": {
                            "$and": [
                                {"$ne": ["$$doc.is_deleted", True]},
                                {"$ne": ["$$doc.is_current", False]},
                                {"$ne": ["$$doc.document_status", "not_available"]},
                            ]
                        },
                    }
                },
                "followups": {
                    "$filter": {
                        "input": "$followups",
                        "as": "follow",
                        "cond": {"$ne": ["$$follow.is_deleted", True]},
                    }
                },
            }
        },
    ]
    p += lookup("application_form_definitions", "form_definition_id", "schema")
    p += [
        {
            "$set": {
                "name": mongo_application_name(),
                "product_name": {"$ifNull": ["$loan_product.name", "$insurance_product.name"]},
                "group_key": {
                    "$cond": [
                        {"$ne": [{"$ifNull": ["$customer._id", None]}, None]},
                        {"$toString": "$customer._id"},
                        {"$concat": ["application:", "$record_id"]},
                    ]
                },
                "assigned_at": {"$ifNull": ["$assigned_at", "$lead.assigned_at"]},
                "assigned_by": {"$ifNull": ["$assigned_by", "$lead.assigned_by"]},
            }
        }
    ]
    p += [
        {
            "$lookup": {
                "from": "audit_logs",
                "let": {"rid": "$record_id"},
                "pipeline": [
                    {
                        "$match": {
                            "event_type": {
                                "$in": [
                                    "application_assigned",
                                    "crm_auto_assigned",
                                    "crm_bulk_assigned",
                                ]
                            },
                            "$expr": {
                                "$or": [
                                    {"$eq": ["$metadata.application_id", "$$rid"]},
                                    {
                                        "$and": [
                                            {"$eq": ["$metadata.collection", "applications"]},
                                            {"$eq": ["$metadata.record_id", "$$rid"]},
                                        ]
                                    },
                                ]
                            },
                        }
                    },
                    {"$sort": {"created_at": -1, "_id": -1}},
                    {"$limit": 1},
                    {"$project": {"created_at": 1, "user_id": 1}},
                ],
                "as": "assignment_audit",
            }
        },
        {
            "$set": {
                "assigned_by": {
                    "$ifNull": ["$assigned_by", {"$arrayElemAt": ["$assignment_audit.user_id", 0]}]
                },
                "assigned_at": {
                    "$ifNull": [
                        "$assigned_at",
                        {"$arrayElemAt": ["$assignment_audit.created_at", 0]},
                    ]
                },
                "name": {
                    "$cond": [
                        {
                            "$and": [
                                {"$eq": ["$record_kind", "lead"]},
                                {"$eq": ["$name", "Name unavailable"]},
                            ]
                        },
                        {"$ifNull": ["$lead.full_name", "$name"]},
                        "$name",
                    ]
                },
            }
        },
    ]
    p += lookup("lead_sources", "lead.source_id", "source")
    p += lookup("branches", "employee.branch_id", "branch")
    p += lookup("designations", "employee.designation_id", "designation")
    p += lookup("users", "assigned_by", "assigner_user")
    p += [
        {
            "$lookup": {
                "from": "employees",
                "localField": "assigned_by",
                "foreignField": "user_id",
                "as": "assigner_employee",
            }
        }
    ]
    criteria: dict[str, Any] = {}
    mapping = {
        "product_id": "product_id",
        "product_category": "product_category",
        "application_status": "status",
        "branch_id": "employee.branch_id",
        "assigned_by": "assigned_by",
        "designation_id": "employee.designation_id",
        "customer_status": "customer.status",
    }
    for key, target in mapping.items():
        value = getattr(f, key)
        if value:
            criteria[target] = value
    if f.source_id:
        if f.source_id.startswith("submission:"):
            criteria["submission_source"] = f.source_id.removeprefix("submission:")
            criteria["lead.source_id"] = None
        else:
            criteria["lead.source_id"] = f.source_id
    if f.customer_id:
        criteria["group_key"] = f.customer_id.lower()
    for target, start, end in [
        ("created_at", f.created_from, f.created_until),
        ("assigned_at", f.assigned_from, f.assigned_until),
    ]:
        bounds = date_range(start, end)
        if bounds:
            criteria[target] = bounds
    follow: dict[str, Any] = {}
    if f.follow_up_status:
        follow["status"] = f.follow_up_status
    if f.follow_up_employee:
        follow["assigned_to"] = f.follow_up_employee
    follow_dates = date_range(f.follow_up_from, f.follow_up_until)
    if f.overdue:
        follow_dates["$lt"] = datetime.now(UTC)
    if follow_dates:
        follow["due_date"] = follow_dates
    if follow:
        criteria["followups"] = {"$elemMatch": follow}
    if f.bank_id:
        criteria["followups.banks.option_id"] = f.bank_id
    if f.document_status in {"pending", "verified", "rejected"}:
        criteria["documents.verification_status"] = f.document_status
    elif f.document_status == "submitted":
        criteria["documents.0"] = {"$exists": True}
    elif f.document_status == "missing":
        p += [
            {
                "$set": {
                    "missing_required": {
                        "$setDifference": [
                            {
                                "$map": {
                                    "input": {
                                        "$filter": {
                                            "input": {
                                                "$ifNull": ["$schema.required_documents", []]
                                            },
                                            "as": "req",
                                            "cond": {"$eq": ["$$req.required", True]},
                                        }
                                    },
                                    "as": "req",
                                    "in": "$$req.document_type_id",
                                }
                            },
                            {
                                "$map": {
                                    "input": "$documents",
                                    "as": "doc",
                                    "in": "$$doc.document_type_id",
                                }
                            },
                        ]
                    }
                }
            }
        ]
        criteria["missing_required.0"] = {"$exists": True}
    if f.search.strip():
        pattern = {"$regex": re.escape(f.search.strip()), "$options": "i"}
        criteria["$or"] = [
            {key: pattern}
            for key in [
                "name",
                "customer.customer_code",
                "application_code",
                "lead.lead_code",
                "customer.mobile",
                "customer.email",
            ]
        ]
    if criteria:
        p += [{"$match": criteria}]
    return p


@router.get("/document-collection/grouped")
async def grouped(
    db: Db,
    actor: Actor,
    filters: Annotated[CollectionFilters, Depends()],
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=200),
    group_key: str | None = Query(None, max_length=80),
) -> ApiResponse[dict[str, Any]]:
    p = await pipeline(db, actor, filters)
    if group_key:
        p += [
            {"$match": {"group_key": group_key}},
            {"$sort": {"submitted_at": -1, "created_at": -1, "_id": -1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {
                            "$project": {
                                "_id": 0,
                                "id": "$record_id",
                                "record_kind": 1,
                                "lead_id": 1,
                                "lead_code": "$lead.lead_code",
                                "application_code": 1,
                                "product_name": 1,
                                "product_category": 1,
                                "status": 1,
                                "assigned_to": 1,
                                "assigned_to_name": "$employee.display_name",
                                "submitted_at": 1,
                                "created_at": 1,
                                "customer_id": {"$toString": "$customer._id"},
                                "customer_code": "$customer.customer_code",
                                "customer_name": "$name",
                                "mobile": {"$ifNull": ["$customer.mobile", "$lead.mobile"]},
                                "source_name": {"$cond": [{"$ne": [{"$ifNull": ["$referral_attribution.partner_id", None]}, None]}, "Referral Partner", "$source.name"]},
                                "referred_by": "$referral_attribution.partner_name",
                                "referral_reference": "$referral_attribution.referral_id",
                                "referral_mode": "$referral_attribution.submission_mode",
                                "source_id": "$lead.source_id",
                                "submission_source": 1,
                                "customer_status": "$customer.status",
                            }
                        },
                    ],
                    "count": [{"$count": "total"}],
                }
            },
        ]
    else:
        p += [
            {"$sort": {"submitted_at": -1, "created_at": -1, "_id": -1}},
            {
                "$group": {
                    "_id": "$group_key",
                    "name": {"$first": "$name"},
                    "customer_code": {"$first": "$customer.customer_code"},
                    "mobile": {"$first": "$customer.mobile"},
                    "application_count": {
                        "$sum": {"$cond": [{"$eq": ["$record_kind", "lead"]}, 0, 1]}
                    },
                    "latest_submission": {"$max": "$submitted_at"},
                    "created_at": {"$max": "$created_at"},
                    "primary": {
                        "$first": {
                            "id": "$record_id",
                            "record_kind": "$record_kind",
                            "lead_id": "$lead_id",
                            "application_code": "$application_code",
                            "product_name": "$product_name",
                            "product_category": "$product_category",
                            "status": "$status",
                            "assigned_to": "$assigned_to",
                            "assigned_to_name": "$employee.display_name",
                            "source_name": {"$cond": [{"$ne": [{"$ifNull": ["$referral_attribution.partner_id", None]}, None]}, "Referral Partner", "$source.name"]},
                                "referred_by": "$referral_attribution.partner_name",
                                "referral_reference": "$referral_attribution.referral_id",
                                "referral_mode": "$referral_attribution.submission_mode",
                            "submission_source": "$submission_source",
                            "customer_status": "$customer.status",
                            "created_at": "$created_at",
                        }
                    },
                }
            },
            {"$sort": {"created_at": -1, "_id": -1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {"$set": {"id": "$_id"}},
                        {"$unset": "_id"},
                    ],
                    "count": [{"$count": "total"}],
                }
            },
        ]
    rows = await db.applications.aggregate(p, allowDiskUse=True).to_list(1)
    data = rows[0] if rows else {"items": [], "count": []}
    return ApiResponse[dict[str, Any]].ok(
        {
            "items": data["items"],
            "total": data["count"][0]["total"] if data["count"] else 0,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/document-collection/filter-options")
async def filter_options(db: Db, actor: Actor) -> ApiResponse[dict[str, Any]]:
    p = await pipeline(db, actor, CollectionFilters())
    dimensions = {
        "product_id": ("$product_id", "$product_name"),
        "assigned_to": ("$assigned_to", "$employee.display_name"),
        "assigned_by": (
            "$assigned_by",
            {
                "$ifNull": [
                    {"$arrayElemAt": ["$assigner_employee.display_name", 0]},
                    "$assigner_user.role",
                ]
            },
        ),
        "source_id": ("$lead.source_id", "$source.name"),
        "branch_id": ("$employee.branch_id", "$branch.name"),
        "follow_up_status": ("$followups.status", "$followups.status"),
        "follow_up_employee": ("$followups.assigned_to", "$followups.assigned_to"),
        "submission_sources": ("$submission_source", "$submission_source"),
        "bank_id": ("$followups.banks.option_id", "$followups.banks.name"),
    }
    facets = {}
    for key, (value, label) in dimensions.items():
        prefix: list[dict[str, Any]] = (
            [{"$unwind": "$followups"}]
            if key in {"follow_up_status", "follow_up_employee", "bank_id"}
            else []
        )
        if key == "bank_id":
            prefix.append({"$unwind": "$followups.banks"})
        if key == "submission_sources":
            prefix.append({"$match": {"lead.source_id": None}})
        facets[key] = prefix + [
            {"$group": {"_id": value, "label": {"$first": label}}},
            {"$match": {"_id": {"$nin": [None, ""]}}},
            {"$limit": 1000},
            {"$project": {"_id": 0, "value": "$_id", "label": 1}},
        ]
    rows = await db.applications.aggregate(p + [{"$facet": facets}], allowDiskUse=True).to_list(1)
    data = rows[0] if rows else {}
    from bson import ObjectId

    from app.features.daily_operations.status_options import COMPANY, INITIAL

    actor_ids = [
        o["value"] for o in data.get("assigned_by", []) if ObjectId.is_valid(o.get("value"))
    ]
    staff = {
        str(u["_id"]): u
        async for u in db.users.find(
            {
                "_id": {"$in": [ObjectId(value) for value in actor_ids]},
                "role": {"$in": ["owner", "employee"]},
                "is_deleted": False,
            },
            {"role": 1},
        )
    }
    names = {
        e["user_id"]: e["display_name"]
        async for e in db.employees.find(
            {"user_id": {"$in": list(staff)}, "is_deleted": False},
            {"user_id": 1, "display_name": 1},
        )
    }
    names.update(
        {
            o["user_id"]: o["full_name"]
            async for o in db.owner_profiles.find(
                {"user_id": {"$in": list(staff)}, "is_deleted": False},
                {"user_id": 1, "full_name": 1},
            )
        }
    )
    data["assigned_by"] = [
        {"value": value, "label": names.get(value) or staff[value]["role"].title()}
        for value in actor_ids
        if value in staff
    ]
    follow_ids = [
        o["value"] for o in data.get("follow_up_employee", []) if ObjectId.is_valid(o.get("value"))
    ]
    data["follow_up_employee"] = [
        {"value": str(e["_id"]), "label": e["display_name"]}
        async for e in db.employees.find(
            {"_id": {"$in": [ObjectId(value) for value in follow_ids]}, "is_deleted": False},
            {"display_name": 1},
        )
    ]
    values = [o["value"] for o in data.get("follow_up_status", [])]
    catalogue = {
        o["value"]: o["name"]
        async for o in db.daily_followup_status_options.find(
            {"company_id": COMPANY, "value": {"$in": values}}, {"value": 1, "name": 1}
        )
    }
    builtins = {value: value.title() for value, _ in INITIAL}
    data["follow_up_status"] = [
        {
            "value": value,
            "label": catalogue.get(value) or builtins.get(value) or "Unavailable follow-up status",
        }
        for value in values
    ]
    sources = {
        str(o["_id"]): o["name"]
        async for o in db.lead_sources.find(
            {"is_deleted": False, "status": "active"}, {"name": 1}
        ).limit(1000)
    }
    sources.update(
        {
            o["value"]: o.get("label") or "Source unavailable"
            for o in data.get("source_id", [])
            if o["value"] not in sources
        }
    )
    data["source_id"] = [{"value": key, "label": label} for key, label in sources.items()]
    for item in data.pop("submission_sources", []):
        value = item.get("value")
        if value and value != "unknown":
            data["source_id"].append(
                {"value": "submission:" + value, "label": value.replace("_", " ").title()}
            )
    for key in data:
        for option in data[key]:
            if not option.get("label"):
                option["label"] = key.removesuffix("_id").replace("_", " ").title() + " unavailable"
        data[key] = sorted(data[key], key=lambda option: str(option.get("label", "")).casefold())
    return ApiResponse[dict[str, Any]].ok(data)
