"""Bounded, permission-scoped Partner metrics from canonical records and ledger."""

from datetime import date, timedelta
from typing import Any

from app.core.exceptions import ForbiddenError, ValidationError
from app.features.referral_partner_management.kyc import PartnerKyc
from app.utils.datetime import ist_date_to_utc_midnight


def dates(start: date | None, end: date | None) -> dict[str, Any]:
    if start and end and start > end:
        raise ValidationError("Start date must be before end date.")
    value = {}
    if start:
        value["$gte"] = ist_date_to_utc_midnight(start)
    if end:
        value["$lt"] = ist_date_to_utc_midnight(end + timedelta(days=1))
    return value


async def metrics(
    db: Any,
    actor: Any,
    *,
    start: date | None = None,
    end: date | None = None,
    partner_id: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    if actor.role == "referral_partner":
        partner = await PartnerKyc(db).partner(actor)
        partner_id = str(partner["_id"])
    elif actor.role != "owner":
        raise ForbiddenError("Partner financial reporting is Owner or self-service only.")
    app_query: dict[str, Any] = {
        "is_deleted": False,
        "referral_attribution.partner_id": partner_id if partner_id else {"$exists": True},
    }
    entry_query: dict[str, Any] = {"is_deleted": False}
    payment_query: dict[str, Any] = {"status": {"$nin": ["initiated", "cancelled"]}}
    if partner_id:
        entry_query["partner_id"] = payment_query["partner_id"] = partner_id
    if product_id:
        app_query["product_id"] = entry_query["product_id"] = product_id
        payment_query["$or"] = [{"product_id": product_id}, {"allocations.product_id": product_id}]
    bounds = dates(start, end)
    if bounds:
        app_query["created_at"] = entry_query["created_at"] = bounds
        payment_query["confirmed_at"] = bounds
    app_results = [
        r
        async for r in db.applications.aggregate(
            [
                {"$match": app_query},
                {"$set": {"application_key": {"$toString": "$_id"}}},
                {
                    "$lookup": {
                        "from": "application_workflows",
                        "localField": "application_key",
                        "foreignField": "application_id",
                        "as": "case",
                    }
                },
                {"$set": {"case": {"$arrayElemAt": ["$case", 0]}}},
                {
                    "$group": {
                        "_id": None,
                        "total_referrals": {"$sum": 1},
                        "draft_referrals": {
                            "$sum": {"$cond": [{"$eq": ["$status", "draft"]}, 1, 0]}
                        },
                        "submitted_referrals": {
                            "$sum": {
                                "$cond": [
                                    {
                                        "$ne": [
                                            {
                                                "$ifNull": [
                                                    "$referral_attribution.submitted_to_afs_at",
                                                    None,
                                                ]
                                            },
                                            None,
                                        ]
                                    },
                                    1,
                                    0,
                                ]
                            }
                        },
                        "document_collection": {
                            "$sum": {
                                "$cond": [
                                    {
                                        "$and": [
                                            {
                                                "$ne": [
                                                    {
                                                        "$ifNull": [
                                                            "$referral_attribution.submitted_to_afs_at",
                                                            None,
                                                        ]
                                                    },
                                                    None,
                                                ]
                                            },
                                            {
                                                "$eq": [
                                                    {"$ifNull": ["$daily_followup_moved_at", None]},
                                                    None,
                                                ]
                                            },
                                            {
                                                "$eq": [
                                                    {
                                                        "$ifNull": [
                                                            "$case.moved_to_loan_management_at",
                                                            None,
                                                        ]
                                                    },
                                                    None,
                                                ]
                                            },
                                        ]
                                    },
                                    1,
                                    0,
                                ]
                            }
                        },
                        "disbursed_loans": {
                            "$sum": {
                                "$cond": [{"$eq": ["$case.current_status", "disbursed"]}, 1, 0]
                            }
                        },
                        "eligible_disbursed_amount": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$case.current_status", "disbursed"]},
                                    "$case.loan_details.disbursed_amount",
                                    0,
                                ]
                            }
                        },
                        "rejected_applications": {
                            "$sum": {"$cond": [{"$eq": ["$case.current_status", "rejected"]}, 1, 0]}
                        },
                    }
                },
            ]
        )
    ]
    result = {
        "total_referrals": 0,
        "draft_referrals": 0,
        "submitted_referrals": 0,
        "document_collection": 0,
        "disbursed_loans": 0,
        "eligible_disbursed_amount": 0,
        "rejected_applications": 0,
        **({k: v for k, v in app_results[0].items() if k != "_id"} if app_results else {}),
    }
    financial_apps: dict[str, Any] = {
        "referral_attribution.partner_id": partner_id if partner_id else {"$exists": True},
        "referral_attribution.submitted_to_afs_at": {"$ne": None},
    }
    legacy_maps: dict[str, Any] = {"partner_id": partner_id} if partner_id else {}
    financial_pipeline: list[dict[str, Any]] = [
        {"$match": financial_apps},
        {"$project": {"application_key": {"$toString": "$_id"}}},
        {
            "$unionWith": {
                "coll": "referral_leads",
                "pipeline": [
                    {"$match": legacy_maps},
                    {
                        "$lookup": {
                            "from": "applications",
                            "localField": "lead_id",
                            "foreignField": "lead_id",
                            "as": "apps",
                        }
                    },
                    {"$unwind": "$apps"},
                    {"$project": {"application_key": {"$toString": "$apps._id"}}},
                ],
            }
        },
        {"$group": {"_id": "$application_key"}},
        {
            "$lookup": {
                "from": "application_workflows",
                "localField": "_id",
                "foreignField": "application_id",
                "as": "case",
            }
        },
        {"$unwind": "$case"},
        {
            "$match": {
                "case.case_type": "loan",
                "case.is_deleted": False,
                "case.loan_details.disbursed_amount": {"$gt": 0},
                **({"case.product_id": product_id} if product_id else {}),
            }
        },
        {
            "$set": {
                "financial_events": {
                    "$cond": [
                        {
                            "$gt": [
                                {
                                    "$size": {
                                        "$ifNull": ["$case.loan_details.disbursement_events", []]
                                    }
                                },
                                0,
                            ]
                        },
                        "$case.loan_details.disbursement_events",
                        [
                            {
                                "amount": "$case.loan_details.disbursed_amount",
                                "at": "$case.loan_details.disbursed_at",
                            }
                        ],
                    ]
                }
            }
        },
        {"$unwind": "$financial_events"},
    ]
    if bounds:
        financial_pipeline.append({"$match": {"financial_events.at": bounds}})
    financial_pipeline.extend(
        [
            {"$group": {"_id": "$case._id", "amount": {"$sum": "$financial_events.amount"}}},
            {"$group": {"_id": None, "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ]
    )
    financial = [r async for r in db.applications.aggregate(financial_pipeline)]
    result["eligible_disbursed_amount"] = round(financial[0]["amount"], 2) if financial else 0
    result["disbursed_loans"] = financial[0]["count"] if financial else 0
    entries = [
        r
        async for r in db.commission_entries.aggregate(
            [
                {"$match": entry_query},
                {
                    "$group": {
                        "_id": "$status",
                        "earned": {
                            "$sum": {
                                "$add": [
                                    "$commission_amount",
                                    {"$ifNull": ["$additional_earned_amount", 0]},
                                ]
                            }
                        },
                        "adjustments": {"$sum": {"$ifNull": ["$adjusted_amount", 0]}},
                        "paid": {
                            "$sum": {
                                "$ifNull": [
                                    "$paid_amount",
                                    {
                                        "$cond": [
                                            {"$eq": ["$status", "paid"]},
                                            "$commission_amount",
                                            0,
                                        ]
                                    },
                                ]
                            }
                        },
                        "reserved": {"$sum": {"$ifNull": ["$reserved_amount", 0]}},
                    }
                },
            ]
        )
    ]
    result.update(
        {
            "commission_adjustments": round(sum(r["adjustments"] for r in entries), 2),
            "commission_earned": round(sum(r["earned"] for r in entries), 2),
            "commission_pending_approval": round(
                sum(
                    r["earned"] + r["adjustments"] - r["paid"]
                    for r in entries
                    if r["_id"] == "pending"
                ),
                2,
            ),
            "commission_payable": round(
                sum(
                    r["earned"] + r["adjustments"] - r["paid"] - r["reserved"]
                    for r in entries
                    if r["_id"] == "approved"
                ),
                2,
            ),
            "commission_reserved": round(sum(r["reserved"] for r in entries), 2),
            "commission_paid": round(sum(r["paid"] for r in entries), 2),
        }
    )
    payment_pipeline: list[dict[str, Any]] = [{"$match": payment_query}]
    if product_id:
        payment_pipeline.append(
            {
                "$set": {
                    "amount": {
                        "$cond": [
                            {"$isArray": "$allocations"},
                            {
                                "$sum": {
                                    "$map": {
                                        "input": {
                                            "$filter": {
                                                "input": "$allocations",
                                                "as": "allocation",
                                                "cond": {
                                                    "$eq": ["$$allocation.product_id", product_id]
                                                },
                                            }
                                        },
                                        "as": "allocation",
                                        "in": "$$allocation.amount",
                                    }
                                }
                            },
                            "$amount",
                        ]
                    }
                }
            }
        )
    payment_pipeline.append({"$group": {"_id": None, "total": {"$sum": "$amount"}}})
    payment_totals = [r async for r in db.commission_payouts.aggregate(payment_pipeline)]
    legacy_paid_query: dict[str, Any] = {
        "is_deleted": False,
        "status": "paid",
        "paid_amount": {"$exists": False},
    }
    if partner_id:
        legacy_paid_query["partner_id"] = partner_id
    if product_id:
        legacy_paid_query["product_id"] = product_id
    if bounds:
        legacy_paid_query["paid_at"] = bounds
    legacy_paid = [
        r
        async for r in db.commission_entries.aggregate(
            [
                {"$match": legacy_paid_query},
                {"$group": {"_id": None, "total": {"$sum": "$commission_amount"}}},
            ]
        )
    ]
    result["commission_paid"] = round(
        (payment_totals[0]["total"] if payment_totals else 0)
        + (legacy_paid[0]["total"] if legacy_paid else 0),
        2,
    )
    if actor.role == "owner":
        partners = [
            r
            async for r in db.referral_partners.aggregate(
                [
                    {"$match": {"is_deleted": False}},
                    {
                        "$group": {
                            "_id": {
                                "kyc": {"$ifNull": ["$kyc_status", "pending"]},
                                "active": {"$ifNull": ["$account_active", True]},
                            },
                            "count": {"$sum": 1},
                        }
                    },
                ]
            )
        ]
        result.update(
            {
                "active_partners": sum(
                    r["count"]
                    for r in partners
                    if r["_id"]["active"] and r["_id"]["kyc"] == "approved"
                ),
                "total_partners": sum(r["count"] for r in partners),
                "kyc_pending": sum(r["count"] for r in partners if r["_id"]["kyc"] == "pending"),
                "kyc_under_review": sum(
                    r["count"] for r in partners if r["_id"]["kyc"] in {"submitted", "under_review"}
                ),
                "kyc_approved": sum(r["count"] for r in partners if r["_id"]["kyc"] == "approved"),
                "suspended_partners": sum(r["count"] for r in partners if not r["_id"]["active"]),
            }
        )
    return result


async def owner_report(
    db: Any,
    actor: Any,
    *,
    partner_id: str | None = None,
    product_id: str | None = None,
    origin: str | None = None,
    application_status: str | None = None,
    disbursement_status: str | None = None,
    commission_status: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Any:
    from app.features.reporting.schemas import ReportColumn, ReportResult

    if actor.role != "owner":
        raise ForbiddenError("Only Owner can view the Partner management report.")
    query: dict[str, Any] = {
        "is_deleted": False,
        "referral_attribution.partner_id": partner_id if partner_id else {"$exists": True},
    }
    for key, value in (
        ("product_id", product_id),
        ("referral_attribution.origin", origin),
        ("status", application_status),
    ):
        if value:
            query[key] = value
    if bounds := dates(start, end):
        query["created_at"] = bounds
    pipeline: list[dict[str, Any]] = [
        {"$match": query},
        {"$set": {"application_key": {"$toString": "$_id"}}},
        {
            "$lookup": {
                "from": "application_workflows",
                "localField": "application_key",
                "foreignField": "application_id",
                "as": "case",
            }
        },
        {"$set": {"case": {"$arrayElemAt": ["$case", 0]}}},
        {"$set": {"case_key": {"$toString": "$case._id"}}},
        {
            "$lookup": {
                "from": "commission_entries",
                "localField": "case_key",
                "foreignField": "case_id",
                "as": "entry",
            }
        },
        {"$set": {"entry": {"$arrayElemAt": ["$entry", 0]}}},
    ]
    if disbursement_status:
        pipeline.append({"$match": {"case.current_status": disbursement_status}})
    if commission_status:
        pipeline.append({"$match": {"entry.status": commission_status}})
    pipeline.extend(
        [
            {"$sort": {"created_at": -1}},
            {"$limit": 10001},
            {
                "$project": {
                    "_id": 0,
                    "application_id": "$application_key",
                    "version": 1,
                    "application_code": 1,
                    "customer_name": "$form_data.full_name",
                    "customer_id": 1,
                    "partner_id": "$referral_attribution.partner_id",
                    "partner_name": "$referral_attribution.partner_name",
                    "referral_id": "$referral_attribution.referral_id",
                    "origin": "$referral_attribution.origin",
                    "submission_mode": "$referral_attribution.submission_mode",
                    "product_id": 1,
                    "application_status": "$status",
                    "case_id": "$case_key",
                    "disbursement_status": "$case.current_status",
                    "eligible_disbursed_amount": {
                        "$ifNull": ["$case.loan_details.disbursed_amount", 0]
                    },
                    "earning_partner_id": "$entry.partner_id",
                    "commission_status": "$entry.status",
                    "commission_earned": {
                        "$add": [
                            {"$ifNull": ["$entry.commission_amount", 0]},
                            {"$ifNull": ["$entry.additional_earned_amount", 0]},
                        ]
                    },
                    "commission_adjustments": {"$ifNull": ["$entry.adjusted_amount", 0]},
                    "commission_paid": {
                        "$ifNull": [
                            "$entry.paid_amount",
                            {
                                "$cond": [
                                    {"$eq": ["$entry.status", "paid"]},
                                    "$entry.commission_amount",
                                    0,
                                ]
                            },
                        ]
                    },
                    "commission_outstanding": {"$ifNull": ["$entry.outstanding_amount", 0]},
                    "commission_reserved": {"$ifNull": ["$entry.reserved_amount", 0]},
                }
            },
        ]
    )
    rows = [row async for row in db.applications.aggregate(pipeline)]
    if len(rows) > 10000:
        raise ValidationError("Narrow the report filters to at most 10000 referrals.")
    labels = {
        "application_code": "Application",
        "customer_name": "Customer",
        "customer_id": "Customer reference",
        "partner_name": "Partner",
        "partner_id": "Partner reference",
        "referral_id": "Referral reference",
        "origin": "Origin",
        "submission_mode": "Submission mode",
        "product_id": "Product reference",
        "application_status": "Application status",
        "case_id": "Loan Case",
        "disbursement_status": "Disbursement status",
        "eligible_disbursed_amount": "Actual disbursed amount",
        "earning_partner_id": "Original earning Partner",
        "commission_status": "Commission status",
        "commission_earned": "Commission earned",
        "commission_adjustments": "Adjustments",
        "commission_paid": "Paid",
        "commission_outstanding": "Outstanding",
        "commission_reserved": "Reserved",
    }
    from decimal import Decimal

    groups: dict[str, dict[str, dict[str, Any]]] = {
        "partner_referrals": {},
        "product_referrals": {},
    }
    for row in rows:
        for name, key in (("partner_referrals", "partner_id"), ("product_referrals", "product_id")):
            reference = row.get(key) or "unavailable"
            group = groups[name].setdefault(
                reference,
                {"reference": reference, "referrals": 0, "eligible_disbursed_amount": Decimal(0)},
            )
            group["referrals"] += 1
            group["eligible_disbursed_amount"] += Decimal(
                str(row.get("eligible_disbursed_amount", 0))
            )
    summary = {
        name: [
            {**group, "eligible_disbursed_amount": float(group["eligible_disbursed_amount"])}
            for group in values.values()
        ]
        for name, values in groups.items()
    }
    return ReportResult(
        columns=[ReportColumn(key=key, label=label) for key, label in labels.items()],
        rows=rows,
        summary=summary,
    )
