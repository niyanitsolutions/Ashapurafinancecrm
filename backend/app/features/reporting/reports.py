"""Module 8 — the Business Reports themselves, on top of the Aggregation Layer
(`aggregations.py`). Per decision 090, most reports are pure `report_definitions` rows
(seeded in `scripts/seed.py:seed_report_definitions`) run by one of three generic
executors below (`_run_count_report`/`_run_sum_report`/`_run_list_report`) — adding one
of those is a new database row, never new Python. A handful of reports have logic that
can't be expressed as generic parameters (a `$lookup` join, a compound group key, a
reused service call, a multi-branch conditional sum) — those stay real functions,
registered in `CUSTOM_REPORT_RUNNERS` by the same `key` their `report_definitions` row
uses. Every function here only reads frozen modules' collections — never writes, never
calls a frozen module's engine.

"Dashboard Analytics" deliberately does not import Dashboard's own `widget_providers.py`
(frozen, and its functions are user-scoped for the calling viewer, a different contract
than a company-wide report) — instead it recomputes the same headline metrics from the
same source collections, so the numbers match Dashboard's own definitions without
modifying a frozen file (decision 084).
"""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.leads.models import Lead
from app.features.referral_partner_management.constants import ExternalLeadStatus
from app.features.referral_partner_management.service import ReferralPartnerManagementService
from app.features.reporting.aggregations import (
    count_matching,
    date_range_match,
    group_count,
    group_sum,
    resolve_names,
)
from app.features.reporting.models import ReportDefinition
from app.features.reporting.schemas import ReportColumn, ReportResult

CustomReportRunner = Callable[[AsyncIOMotorDatabase[Any], date | None, date | None], Awaitable[ReportResult]]


def _label_from_id(value: str | None, names: dict[str, str], *, fallback: str = "Unassigned") -> str:
    if value is None:
        return fallback
    return names.get(value, value)


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def _get_nested(doc: dict[str, Any], dotted_field: str) -> Any:
    value: Any = doc
    for part in dotted_field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _columns(definition: ReportDefinition) -> list[ReportColumn]:
    return [ReportColumn(key=c.key, label=c.label) for c in definition.columns]


# ============================================================================== generic executors (report_type: count / sum / list)


async def run_count_report(db: AsyncIOMotorDatabase[Any], definition: ReportDefinition, date_from: date | None, date_to: date | None) -> ReportResult:
    assert definition.collection and definition.group_field and definition.date_field
    grouped = await group_count(
        db, definition.collection, group_field=definition.group_field, date_field=definition.date_field, date_from=date_from, date_to=date_to,
        extra_match=definition.extra_match or None,
    )
    names: dict[str, str] = {}
    if definition.name_resolution_collection:
        names = await resolve_names(
            db, definition.name_resolution_collection, {g["group_value"] for g in grouped if g["group_value"]}, name_field=definition.name_resolution_field or "name"
        )
    dim_key, metric_key = definition.columns[0].key, definition.columns[1].key
    rows = []
    for g in grouped:
        value = g["group_value"]
        label = _label_from_id(value, names) if names else _humanize(value)
        rows.append({dim_key: label, metric_key: g["count"]})
    return ReportResult(columns=_columns(definition), rows=rows)


async def run_sum_report(db: AsyncIOMotorDatabase[Any], definition: ReportDefinition, date_from: date | None, date_to: date | None) -> ReportResult:
    assert definition.collection and definition.group_field and definition.sum_field and definition.date_field
    grouped = await group_sum(
        db, definition.collection, group_field=definition.group_field, sum_field=definition.sum_field, date_field=definition.date_field,
        date_from=date_from, date_to=date_to, extra_match=definition.extra_match or None,
    )
    dim_key, count_key, total_key = definition.columns[0].key, definition.columns[1].key, definition.columns[2].key
    rows = [{dim_key: g["group_value"] or "Unspecified", count_key: g["count"], total_key: g["total"]} for g in grouped]
    return ReportResult(columns=_columns(definition), rows=rows)


async def run_list_report(db: AsyncIOMotorDatabase[Any], definition: ReportDefinition, date_from: date | None, date_to: date | None) -> ReportResult:
    assert definition.collection and definition.date_field
    case_type = definition.extra_match.get("case_type")
    match = {"is_deleted": False, **definition.extra_match, **date_range_match(definition.date_field, date_from, date_to)}
    cursor = db[definition.collection].find(match).sort(definition.date_field, -1).limit(500)
    rows = []
    async for doc in cursor:
        amount = None
        if definition.amount_field:
            details = doc.get("loan_details") if case_type == "loan" else doc.get("insurance_details")
            amount = (details or {}).get(definition.amount_field)
        date_value = _get_nested(doc, definition.date_field)
        rows.append({"case_code": doc["case_code"], "status": _humanize(doc["current_status"]), "amount": amount, "date": date_value.isoformat() if date_value else None})
    summary: dict[str, Any] = {"total": len(rows)}
    if definition.amount_field:
        summary["total_amount"] = sum(r["amount"] or 0 for r in rows)
    return ReportResult(columns=_columns(definition), rows=rows, summary=summary)


# ============================================================================== custom reports (report_type: custom)


async def _lead_conversion(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    pipeline = [
        {"$match": match},
        {"$addFields": {"_id_str": {"$toString": "$_id"}}},
        {"$lookup": {"from": "applications", "localField": "_id_str", "foreignField": "lead_id", "as": "apps"}},
        {"$group": {"_id": "$source_id", "total": {"$sum": 1}, "converted": {"$sum": {"$cond": [{"$gt": [{"$size": "$apps"}, 0]}, 1, 0]}}}},
        {"$sort": {"total": -1}},
    ]
    grouped = [doc async for doc in db["leads"].aggregate(pipeline)]
    names = await resolve_names(db, "lead_sources", {d["_id"] for d in grouped if d["_id"]})
    rows = [
        {
            "source": _label_from_id(d["_id"], names, fallback="Unknown"), "total_leads": d["total"], "converted": d["converted"],
            "conversion_rate_pct": round(100 * d["converted"] / d["total"], 1) if d["total"] else 0.0,
        }
        for d in grouped
    ]
    return ReportResult(
        columns=[
            ReportColumn(key="source", label="Source"), ReportColumn(key="total_leads", label="Total Leads"),
            ReportColumn(key="converted", label="Converted"), ReportColumn(key="conversion_rate_pct", label="Conversion %"),
        ],
        rows=rows,
    )


async def _lead_by_product(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"product_category": "$product_category", "product_id": "$product_id"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    grouped = [doc async for doc in db["leads"].aggregate(pipeline)]
    loan_ids = {d["_id"]["product_id"] for d in grouped if d["_id"]["product_category"] == "loan"}
    insurance_ids = {d["_id"]["product_id"] for d in grouped if d["_id"]["product_category"] == "insurance"}
    loan_names = await resolve_names(db, "loan_products", loan_ids)
    insurance_names = await resolve_names(db, "insurance_products", insurance_ids)
    rows = []
    for d in grouped:
        category, product_id = d["_id"]["product_category"], d["_id"]["product_id"]
        names = loan_names if category == "loan" else insurance_names
        rows.append({"product_category": _humanize(category), "product": names.get(product_id, product_id), "count": d["count"]})
    return ReportResult(
        columns=[
            ReportColumn(key="product_category", label="Category"), ReportColumn(key="product", label="Product"), ReportColumn(key="count", label="Leads"),
        ],
        rows=rows,
    )


async def _employee_task_summary(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$assigned_to", "assigned": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
            }
        },
        {"$sort": {"assigned": -1}},
    ]
    grouped = [doc async for doc in db["tasks"].aggregate(pipeline)]
    names = await resolve_names(db, "employees", {d["_id"] for d in grouped if d["_id"]}, name_field="display_name")
    rows = [{"employee": _label_from_id(d["_id"], names), "assigned": d["assigned"], "completed": d["completed"], "pending": d["pending"]} for d in grouped]
    return ReportResult(
        columns=[
            ReportColumn(key="employee", label="Employee"), ReportColumn(key="assigned", label="Assigned"),
            ReportColumn(key="completed", label="Completed"), ReportColumn(key="pending", label="Pending"),
        ],
        rows=rows,
    )


async def _referral_leads(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    mappings = [doc async for doc in db["referral_leads"].find(match).sort("created_at", -1).limit(500)]
    partner_names = await resolve_names(db, "referral_partners", {m["partner_id"] for m in mappings}, name_field="full_name")
    service = ReferralPartnerManagementService(db)
    lead_ids = [m["lead_id"] for m in mappings]
    leads_by_id = {str(doc["_id"]): doc async for doc in db["leads"].find({"_id": {"$in": [ObjectId(i) for i in lead_ids]}})}
    rows = []
    for mapping in mappings:
        lead_doc = leads_by_id.get(mapping["lead_id"])
        if lead_doc is None:
            continue
        lead = Lead.model_validate(lead_doc)
        status, _editable = await service.external_status_and_editable(lead)
        rows.append({
            "partner": partner_names.get(mapping["partner_id"], mapping["partner_id"]), "lead_code": lead.lead_code,
            "full_name": lead.full_name, "external_status": _humanize(status), "submitted_at": lead.created_at.isoformat(),
        })
    return ReportResult(
        columns=[
            ReportColumn(key="partner", label="Referral Partner"), ReportColumn(key="lead_code", label="Lead"),
            ReportColumn(key="full_name", label="Name"), ReportColumn(key="external_status", label="Status"),
            ReportColumn(key="submitted_at", label="Submitted At"),
        ],
        rows=rows,
    )


async def _referral_conversions(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    mappings = [doc async for doc in db["referral_leads"].find(match)]
    by_partner: dict[str, list[str]] = {}
    for m in mappings:
        by_partner.setdefault(m["partner_id"], []).append(m["lead_id"])

    service = ReferralPartnerManagementService(db)
    partner_names = await resolve_names(db, "referral_partners", set(by_partner), name_field="full_name")
    rows: list[dict[str, Any]] = []
    for partner_id, lead_ids in by_partner.items():
        approved = 0
        for lead_id in lead_ids:
            lead_doc = await db["leads"].find_one({"_id": ObjectId(lead_id)})
            if lead_doc is None:
                continue
            status, _editable = await service.external_status_and_editable(Lead.model_validate(lead_doc))
            if status == ExternalLeadStatus.APPROVED:
                approved += 1
        total = len(lead_ids)
        rows.append({
            "partner": partner_names.get(partner_id, partner_id), "total_leads": total, "approved": approved,
            "conversion_rate_pct": round(100 * approved / total, 1) if total else 0.0,
        })
    rows.sort(key=lambda r: r["total_leads"], reverse=True)
    return ReportResult(
        columns=[
            ReportColumn(key="partner", label="Referral Partner"), ReportColumn(key="total_leads", label="Total Leads"),
            ReportColumn(key="approved", label="Approved"), ReportColumn(key="conversion_rate_pct", label="Conversion %"),
        ],
        rows=rows,
    )


async def _referral_commission(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    match = {"is_deleted": False, **date_range_match("created_at", date_from, date_to)}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$partner_id",
                "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, "$commission_amount", 0]}},
                "approved": {"$sum": {"$cond": [{"$eq": ["$status", "approved"]}, "$commission_amount", 0]}},
                "paid": {"$sum": {"$cond": [{"$eq": ["$status", "paid"]}, "$commission_amount", 0]}},
            }
        },
        {"$sort": {"paid": -1}},
    ]
    grouped = [doc async for doc in db["commission_entries"].aggregate(pipeline)]
    names = await resolve_names(db, "referral_partners", {d["_id"] for d in grouped if d["_id"]}, name_field="full_name")
    rows = [
        {
            "partner": names.get(d["_id"], d["_id"]), "commission_pending": d["pending"], "commission_approved": d["approved"], "commission_paid": d["paid"],
            "commission_balance": d["pending"] + d["approved"],
        }
        for d in grouped
    ]
    return ReportResult(
        columns=[
            ReportColumn(key="partner", label="Referral Partner"), ReportColumn(key="commission_pending", label="Pending"),
            ReportColumn(key="commission_approved", label="Approved"), ReportColumn(key="commission_paid", label="Paid"),
            ReportColumn(key="commission_balance", label="Balance"),
        ],
        rows=rows,
    )


async def _dashboard_analytics(db: AsyncIOMotorDatabase[Any], date_from: date | None, date_to: date | None) -> ReportResult:
    total_leads = await count_matching(db, "leads", date_field="created_at", date_from=date_from, date_to=date_to)
    assigned_leads = await count_matching(db, "leads", date_field="created_at", date_from=date_from, date_to=date_to, extra_match={"assigned_to": {"$ne": None}})
    disbursed = await count_matching(
        db, "application_workflows", date_field="loan_details.disbursed_at", date_from=date_from, date_to=date_to, extra_match={"case_type": "loan", "current_status": "disbursed"}
    )
    policies_issued = await count_matching(
        db, "application_workflows", date_field="insurance_details.policy_issued_at", date_from=date_from, date_to=date_to,
        extra_match={"case_type": "insurance", "current_status": "policy_issued"},
    )
    pending_tasks = await count_matching(db, "tasks", date_field="created_at", date_from=date_from, date_to=date_to, extra_match={"status": "pending"})
    active_partners = await db["referral_partners"].count_documents({"is_deleted": False, "approval_status": "active"})

    summary = {
        "total_leads": total_leads, "assigned_leads": assigned_leads, "loans_disbursed": disbursed, "policies_issued": policies_issued,
        "pending_tasks": pending_tasks, "active_referral_partners": active_partners,
    }
    rows = [{"metric": label, "value": value} for label, value in [
        ("Total Leads", total_leads), ("Assigned Leads", assigned_leads), ("Loans Disbursed", disbursed),
        ("Insurance Policies Issued", policies_issued), ("Pending Tasks", pending_tasks), ("Active Referral Partners", active_partners),
    ]]
    return ReportResult(columns=[ReportColumn(key="metric", label="Metric"), ReportColumn(key="value", label="Value")], rows=rows, summary=summary)


CUSTOM_REPORT_RUNNERS: dict[str, CustomReportRunner] = {
    "lead_conversion": _lead_conversion,
    "lead_by_product": _lead_by_product,
    "employee_task_summary": _employee_task_summary,
    "referral_leads": _referral_leads,
    "referral_conversions": _referral_conversions,
    "referral_commission": _referral_commission,
    "dashboard_analytics": _dashboard_analytics,
}
