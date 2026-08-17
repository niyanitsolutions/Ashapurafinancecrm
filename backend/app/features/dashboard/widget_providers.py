"""The actual "Dashboard Engine" data computation — one async function per widget `key`,
registered in `WIDGET_PROVIDERS`. This is code, not DB-driven data (unlike the widget
*catalog*, which is), for the same reason Access Control's `PermissionEngine` is code
while its `Permission` catalog is data: computing a real value requires real logic.

Widgets whose owning module doesn't exist yet (Document Management, Reporting) use
`_not_yet_available`/`_not_yet_available_list` — an honest `available: False` + zero/
empty value, never a fabricated number. See docs/decisions/DECISIONS.md #032. Leads
(`_today_leads`/`_assigned_leads`, decision 044), Loan/Insurance Management
(`_disbursed`/`_rejected`, Module 6C), Reminders (`_tasks`/`_notifications`, Module 6D),
and Referral Partner Management (`_referral_summary`, Module 7) are the modules that have
since wired their widgets to real data. `pending_followups` stays a placeholder even
after Module 6D — it needs a follow-up-date field on `Lead` that Module 6A's frozen
schema doesn't have, which is a different concept from 6D's re-eligibility/task
reminders.

Phase 4 (Employee Dashboard & Dynamic Navigation) added 25 more real widgets — business
KPIs (Total Leads, Customers, Applications, Loan/Insurance Cases, Policies Issued,
Re-Eligible, Revenue, Commission), performance widgets (Today's/Monthly Performance,
Lead Conversion, Tasks Completed), and charts (Lead Source, Loan/Insurance Pipeline,
Employee/Referral Performance, Revenue Trend). Every one follows the exact same rules
already established here: Owner-vs-Employee scoping via `_scope_to_employee`, and an
honest `available: False` rather than a fabricated number wherever the underlying data
genuinely doesn't exist yet (e.g. no active re-eligibility rule for a case type).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import OWNER
from app.features.auth.models import User
from app.utils.datetime import (
    ist_month_start_utc,
    now_ist,
    start_of_day_ist,
    start_of_month_ist,
    to_ist,
    utc_now,
)
from app.utils.helpers import to_object_id

WidgetProvider = Callable[[AsyncIOMotorDatabase[Any], User], Awaitable[dict[str, Any]]]

_NO_EMPLOYEE_SENTINEL = "___no_employee___"


async def _scope_to_employee(db: AsyncIOMotorDatabase[Any], user: User) -> str | None:
    """Phase 4 shared helper — `None` for Owner (no scoping, company-wide), or the
    employee_id an Employee's queries should filter on. Returns a sentinel that matches
    no real document if the Employee has no employee record (same "never error, just
    return zero" convention every existing widget in this file already follows inline)."""
    if user.role == OWNER:
        return None
    employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
    return str(employee["_id"]) if employee else _NO_EMPLOYEE_SENTINEL


async def _day_over_day_trend(
    db: AsyncIOMotorDatabase[Any], collection_name: str, base_query: dict[str, Any], date_field: str, now: datetime
) -> dict[str, Any]:
    """Phase 4.1 Widget Standard pilot — "Trend" + "Comparison" for a widget whose
    headline is a cumulative count: how many new matching records landed today vs
    yesterday. Only applied to the two Phase 4 widgets piloting the new standard
    (`applications_submitted`, `tasks_completed`) — not retrofitted onto every widget
    in one pass; see the Phase 4.1 report for which widgets keep the simpler shape."""
    # "Today"/"yesterday" mean the business (IST) calendar day, not UTC midnight — see
    # app/utils/datetime.py.
    start_of_today = start_of_day_ist(now)
    start_of_yesterday = start_of_today - timedelta(days=1)
    today_count = await db[collection_name].count_documents({**base_query, date_field: {"$gte": start_of_today}})
    yesterday_count = await db[collection_name].count_documents(
        {**base_query, date_field: {"$gte": start_of_yesterday, "$lt": start_of_today}}
    )
    if yesterday_count == 0:
        percent = 100 if today_count > 0 else 0
    else:
        percent = round(((today_count - yesterday_count) / yesterday_count) * 100)
    direction = "up" if today_count > yesterday_count else "down" if today_count < yesterday_count else "flat"
    return {
        "trend_direction": direction,
        "trend_percent": abs(percent),
        "comparison_label": "Compared to yesterday",
        "last_updated": now.isoformat(),
    }


async def _not_yet_available(_db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    return {"available": False, "value": 0}


async def _not_yet_available_list(_db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    return {"available": False, "items": []}


async def _employee_summary(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    total = await db["employees"].count_documents({"is_deleted": False})
    active = await db["employees"].count_documents({"is_deleted": False, "status": "active"})
    return {"available": True, "total": total, "active": active, "inactive": total - active}


async def _department_summary(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    departments = await db["departments"].find({"is_deleted": False}).to_list(length=500)
    items = []
    for dept in departments:
        count = await db["employees"].count_documents({"is_deleted": False, "department_id": str(dept["_id"])})
        items.append({"name": dept["name"], "employee_count": count})
    return {"available": True, "items": items}


async def _today_leads(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # "Today" means the business (IST) calendar day, not UTC midnight.
    start_of_day = start_of_day_ist()
    query: dict[str, Any] = {"is_deleted": False, "created_at": {"$gte": start_of_day}}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["leads"].count_documents(query)
    return {"available": True, "value": count}


async def _assigned_leads(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Owner sees every assigned lead company-wide; an Employee sees their own assignment
    # count only — the same Owner-vs-Employee scoping convention as Recent Activities.
    query: dict[str, Any] = {"is_deleted": False, "assigned_to": {"$ne": None}}
    if user.role != OWNER:
        employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
        if employee is None:
            return {"available": True, "value": 0}
        query["assigned_to"] = str(employee["_id"])
    count = await db["leads"].count_documents(query)
    return {"available": True, "value": count}


async def _disbursed(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Module 6C: counts Loan Cases (application_workflows, case_type="loan") currently
    # in the terminal "disbursed" status — Owner sees the company-wide count, an
    # Employee only their own assigned cases, same scoping convention as Assigned Leads.
    query: dict[str, Any] = {"is_deleted": False, "case_type": "loan", "current_status": "disbursed"}
    if user.role != OWNER:
        employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
        if employee is None:
            return {"available": True, "value": 0}
        query["assigned_to"] = str(employee["_id"])
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _rejected(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Module 6C: counts both Loan and Insurance Cases currently "rejected" — the same
    # Owner-vs-Employee scoping as Disbursed above.
    query: dict[str, Any] = {"is_deleted": False, "current_status": "rejected"}
    if user.role != OWNER:
        employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
        if employee is None:
            return {"available": True, "value": 0}
        query["assigned_to"] = str(employee["_id"])
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _tasks(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Module 6D: an Employee's own pending tasks; Owner sees every pending task
    # company-wide (same convention as Recent Activities' Owner/Employee split).
    query: dict[str, Any] = {"is_deleted": False, "status": "pending"}
    if user.role != OWNER:
        employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
        if employee is None:
            return {"available": True, "items": []}
        query["assigned_to"] = str(employee["_id"])
    cursor = db["tasks"].find(query).sort("due_at", 1).limit(10)
    items = [{"title": doc["title"], "due_at": doc["due_at"].isoformat() if doc.get("due_at") else None} async for doc in cursor]
    return {"available": True, "items": items}


async def _notifications(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Module 6D: the calling user's own notification inbox — never another user's,
    # regardless of role (Owner doesn't get to read Employees' personal notifications
    # just by bypassing permission checks elsewhere).
    unread_count = await db["notifications"].count_documents({"is_deleted": False, "recipient_user_id": user.require_id(), "status": "unread"})
    cursor = db["notifications"].find({"is_deleted": False, "recipient_user_id": user.require_id()}).sort("created_at", -1).limit(10)
    items = [
        {"title": doc["title"], "message": doc["message"], "status": doc["status"], "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None}
        async for doc in cursor
    ]
    return {"available": True, "items": items, "unread_count": unread_count}


async def _recent_activities(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Owner sees system-wide recent activity; an Employee (even one granted this widget)
    # only ever sees their own — a distinct, more sensitive concern than "can see this
    # widget exists" (see decision 032).
    query: dict[str, Any] = {} if user.role == OWNER else {"user_id": user.require_id()}
    cursor = db["audit_logs"].find(query).sort("created_at", -1).limit(10)
    items = [
        {"event_type": doc["event_type"], "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None}
        async for doc in cursor
    ]
    return {"available": True, "items": items}


async def _referral_summary(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # Module 7 — company-wide totals; only Owner ever sees this widget in practice
    # (no Employee permission is ever seeded for referral_partner_management, per the
    # brief framing every capability here as Owner-only), so no per-user scoping needed.
    total = await db["referral_partners"].count_documents({"is_deleted": False})
    active = await db["referral_partners"].count_documents({"is_deleted": False, "approval_status": "active"})
    pending_approval = await db["referral_partners"].count_documents({"is_deleted": False, "approval_status": "pending_approval"})
    return {"available": True, "total_partners": total, "active_partners": active, "pending_approval": pending_approval}


async def _total_leads(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["leads"].count_documents(query)
    return {"available": True, "value": count}


async def _customers_summary(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Gated by `required_module=None` (inherent visibility, not a delegable permission —
    # decision 050), same as Dashboard's own base widgets. An Employee's count is scoped
    # to customers reachable via their own assigned applications, mirroring
    # `CustomerService.list_customers_for_staff`'s own scoping (read-only reuse of the
    # same idea, not a call into that frozen module).
    if user.role == OWNER:
        total = await db["customers"].count_documents({"is_deleted": False})
        return {"available": True, "value": total}
    employee = await db["employees"].find_one({"user_id": user.require_id(), "is_deleted": False})
    if employee is None:
        return {"available": True, "value": 0}
    customer_ids = await db["applications"].distinct(
        "customer_id", {"is_deleted": False, "assigned_to": str(employee["_id"]), "customer_id": {"$ne": None}}
    )
    return {"available": True, "value": len(customer_ids)}


async def _applications_summary(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    total = await db["applications"].count_documents(query)
    submitted = await db["applications"].count_documents({**query, "status": "submitted"})
    return {"available": True, "total": total, "draft": total - submitted, "submitted": submitted}


async def _applications_submitted(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False, "status": "submitted"}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["applications"].count_documents(query)
    trend = await _day_over_day_trend(db, "applications", query, "submitted_at", utc_now())
    return {"available": True, "value": count, **trend}


async def _loan_cases_total(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # "In my/the company's active pipeline right now" — excludes the two terminal
    # statuses (already covered by the existing Disbursed/Rejected widgets).
    query: dict[str, Any] = {"is_deleted": False, "case_type": "loan", "current_status": {"$nin": ["disbursed", "rejected"]}}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _insurance_cases_total(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False, "case_type": "insurance", "current_status": {"$nin": ["policy_issued", "rejected"]}}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _policies_issued(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False, "case_type": "insurance", "current_status": "policy_issued"}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _insurance_rejected(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # Distinct from the existing (loan_management-gated, loan+insurance-combined)
    # `rejected` widget — this one is insurance_management-gated and insurance-only, so
    # an Employee granted only Insurance Management still gets a Rejected figure.
    query: dict[str, Any] = {"is_deleted": False, "case_type": "insurance", "current_status": "rejected"}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _re_eligible_count(db: AsyncIOMotorDatabase[Any], user: User, case_type: str) -> dict[str, Any]:
    # Reuses the exact re-eligibility rule Module 6D's `check_re_eligible_cases` scheduled
    # job already reads (`reminder_rules`, rule_type="re_eligibility") — read-only, no
    # change to that job. Approximates "rejected_at" as `updated_at` (the same fallback
    # the job itself uses when no status-history entry exists) rather than doing a full
    # history lookup per case, since this is a dashboard KPI, not the reminder trigger
    # itself — honestly reported as unavailable if no active rule exists for this
    # case_type, never a fabricated number.
    rule = await db["reminder_rules"].find_one(
        {"is_deleted": False, "status": "active", "rule_type": "re_eligibility", "case_type": case_type}
    )
    if rule is None or rule.get("eligible_after_days") is None:
        return {"available": False, "value": 0}
    threshold = utc_now() - timedelta(days=rule["eligible_after_days"])
    query: dict[str, Any] = {
        "is_deleted": False, "case_type": case_type, "current_status": "rejected", "updated_at": {"$lte": threshold}
    }
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["application_workflows"].count_documents(query)
    return {"available": True, "value": count}


async def _loan_re_eligible(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    return await _re_eligible_count(db, user, "loan")


async def _insurance_re_eligible(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    return await _re_eligible_count(db, user, "insurance")


async def _tasks_completed(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False, "status": "completed"}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    count = await db["tasks"].count_documents(query)
    trend = await _day_over_day_trend(db, "tasks", query, "completed_at", utc_now())
    return {"available": True, "value": count, **trend}


async def _lead_conversion_rate(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    lead_ids = await db["leads"].distinct("_id", query)
    if not lead_ids:
        return {"available": True, "value": 0}
    lead_id_strs = [str(lid) for lid in lead_ids]
    converted = await db["applications"].count_documents({"is_deleted": False, "lead_id": {"$in": lead_id_strs}, "status": "submitted"})
    return {"available": True, "value": round((converted / len(lead_ids)) * 100)}


async def _performance_summary(db: AsyncIOMotorDatabase[Any], user: User, *, since: datetime) -> dict[str, Any]:
    employee_id = await _scope_to_employee(db, user)

    leads_query: dict[str, Any] = {"is_deleted": False, "created_at": {"$gte": since}}
    apps_query: dict[str, Any] = {"is_deleted": False, "status": "submitted", "submitted_at": {"$gte": since}}
    tasks_query: dict[str, Any] = {"is_deleted": False, "status": "completed", "completed_at": {"$gte": since}}
    if employee_id is not None:
        leads_query["assigned_to"] = employee_id
        apps_query["assigned_to"] = employee_id
        tasks_query["assigned_to"] = employee_id

    leads_count = await db["leads"].count_documents(leads_query)
    apps_count = await db["applications"].count_documents(apps_query)
    tasks_count = await db["tasks"].count_documents(tasks_query)
    return {"available": True, "leads": leads_count, "applications": apps_count, "tasks": tasks_count}


async def _today_performance(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # "Today" means the business (IST) calendar day, not UTC midnight.
    return await _performance_summary(db, user, since=start_of_day_ist())


async def _monthly_performance(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    # "This month" means the business (IST) calendar month, not UTC midnight of the 1st.
    return await _performance_summary(db, user, since=start_of_month_ist())


async def _lead_source_chart(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    rows = await db["leads"].aggregate([{"$match": query}, {"$group": {"_id": "$source_id", "count": {"$sum": 1}}}]).to_list(length=100)
    source_ids = [r["_id"] for r in rows if r["_id"]]
    sources = (
        await db["lead_sources"].find({"_id": {"$in": [to_object_id(s) for s in source_ids]}}).to_list(length=100) if source_ids else []
    )
    name_map = {str(s["_id"]): s["name"] for s in sources}
    items = [{"label": name_map.get(r["_id"], "Unknown"), "value": r["count"]} for r in rows]
    return {"available": True, "items": items}


async def _pipeline_chart(db: AsyncIOMotorDatabase[Any], user: User, case_type: str) -> dict[str, Any]:
    query: dict[str, Any] = {"is_deleted": False, "case_type": case_type}
    employee_id = await _scope_to_employee(db, user)
    if employee_id is not None:
        query["assigned_to"] = employee_id
    rows = await db["application_workflows"].aggregate(
        [{"$match": query}, {"$group": {"_id": "$current_status", "count": {"$sum": 1}}}]
    ).to_list(length=50)
    definitions = await db["workflow_definitions"].find({"case_type": case_type, "is_deleted": False}).to_list(length=50)
    label_map = {d["status"]: d["label"] for d in definitions}
    items = [{"label": label_map.get(r["_id"], r["_id"]), "value": r["count"]} for r in rows]
    return {"available": True, "items": items}


async def _loan_pipeline_chart(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    return await _pipeline_chart(db, user, "loan")


async def _insurance_pipeline_chart(db: AsyncIOMotorDatabase[Any], user: User) -> dict[str, Any]:
    return await _pipeline_chart(db, user, "insurance")


async def _employee_performance_chart(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # Company-wide by nature (ranks employees against each other) — same posture as the
    # existing Department/Employee Summary widgets under this same permission.
    rows = await db["application_workflows"].aggregate(
        [
            {"$match": {"is_deleted": False, "current_status": {"$in": ["disbursed", "policy_issued"]}, "assigned_to": {"$ne": None}}},
            {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
    ).to_list(length=10)
    employee_ids = [r["_id"] for r in rows]
    employees = (
        await db["employees"].find({"_id": {"$in": [to_object_id(e) for e in employee_ids]}}).to_list(length=10) if employee_ids else []
    )
    name_map = {str(e["_id"]): e["display_name"] for e in employees}
    items = [{"label": name_map.get(r["_id"], "Unknown"), "value": r["count"]} for r in rows]
    return {"available": True, "items": items}


async def _referral_pending_commission(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # Owner-only in practice (referral_partner_management has no seeded Permission
    # catalog entry — see decision 081), same construction as `_referral_summary`.
    rows = await db["commission_entries"].aggregate(
        [
            {"$match": {"is_deleted": False, "status": {"$in": ["pending", "approved"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$commission_amount"}, "count": {"$sum": 1}}},
        ]
    ).to_list(length=1)
    row = rows[0] if rows else {"total": 0, "count": 0}
    return {"available": True, "value": row.get("count", 0), "amount": round(row.get("total", 0), 2)}


async def _referral_paid_commission(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    rows = await db["commission_entries"].aggregate(
        [
            {"$match": {"is_deleted": False, "status": "paid"}},
            {"$group": {"_id": None, "total": {"$sum": "$commission_amount"}, "count": {"$sum": 1}}},
        ]
    ).to_list(length=1)
    row = rows[0] if rows else {"total": 0, "count": 0}
    return {"available": True, "value": row.get("count", 0), "amount": round(row.get("total", 0), 2)}


async def _referral_performance_chart(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    rows = await db["commission_entries"].aggregate(
        [
            {"$match": {"is_deleted": False}},
            {"$group": {"_id": "$partner_id", "total": {"$sum": "$commission_amount"}}},
            {"$sort": {"total": -1}},
            {"$limit": 10},
        ]
    ).to_list(length=10)
    partner_ids = [r["_id"] for r in rows]
    partners = (
        await db["referral_partners"].find({"_id": {"$in": [to_object_id(p) for p in partner_ids]}}).to_list(length=10)
        if partner_ids
        else []
    )
    name_map = {str(p["_id"]): p["full_name"] for p in partners}
    items = [{"label": name_map.get(r["_id"], "Unknown"), "value": round(r["total"], 2)} for r in rows]
    return {"available": True, "items": items}


async def _loan_revenue(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # Owner-only in practice (reporting/revenue has no seeded Permission catalog entry —
    # same construction the existing `revenue` widget already established). Real
    # money, not fabricated: `loan_details.offered_amount` on disbursed cases.
    rows = await db["application_workflows"].aggregate(
        [
            {"$match": {"is_deleted": False, "case_type": "loan", "current_status": "disbursed", "loan_details.offered_amount": {"$ne": None}}},
            {"$group": {"_id": None, "total": {"$sum": "$loan_details.offered_amount"}}},
        ]
    ).to_list(length=1)
    return {"available": True, "value": round(rows[0]["total"], 2) if rows else 0}


async def _insurance_revenue(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    rows = await db["application_workflows"].aggregate(
        [
            {
                "$match": {
                    "is_deleted": False, "case_type": "insurance", "current_status": "policy_issued",
                    "insurance_details.premium_amount": {"$ne": None},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$insurance_details.premium_amount"}}},
        ]
    ).to_list(length=1)
    return {"available": True, "value": round(rows[0]["total"], 2) if rows else 0}


async def _monthly_revenue(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # "This month" means the business (IST) calendar month, not UTC midnight of the 1st.
    start_of_month = start_of_month_ist()
    loan_rows = await db["application_workflows"].aggregate(
        [
            {
                "$match": {
                    "is_deleted": False, "case_type": "loan", "current_status": "disbursed",
                    "updated_at": {"$gte": start_of_month}, "loan_details.offered_amount": {"$ne": None},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$loan_details.offered_amount"}}},
        ]
    ).to_list(length=1)
    insurance_rows = await db["application_workflows"].aggregate(
        [
            {
                "$match": {
                    "is_deleted": False, "case_type": "insurance", "current_status": "policy_issued",
                    "updated_at": {"$gte": start_of_month}, "insurance_details.premium_amount": {"$ne": None},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$insurance_details.premium_amount"}}},
        ]
    ).to_list(length=1)
    loan_total = loan_rows[0]["total"] if loan_rows else 0
    insurance_total = insurance_rows[0]["total"] if insurance_rows else 0
    return {"available": True, "value": round(loan_total + insurance_total, 2), "loan": round(loan_total, 2), "insurance": round(insurance_total, 2)}


async def _revenue_trend_chart(db: AsyncIOMotorDatabase[Any], _user: User) -> dict[str, Any]:
    # Last 6 calendar months (business/IST calendar, not UTC — see app/utils/datetime.py)
    # — approximates "when revenue happened" via `updated_at` (the same approximation
    # decision 088/089 already accepted for Reporting, since `ApplicationWorkflow` has
    # no dedicated `disbursed_at` field), real amounts only.
    now = now_ist()
    months: list[tuple[int, int]] = []
    y, m = now.year, now.month
    for _ in range(6):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    range_start = ist_month_start_utc(months[0][0], months[0][1])

    totals: dict[tuple[int, int], float] = dict.fromkeys(months, 0.0)
    cursor = db["application_workflows"].find(
        {
            "is_deleted": False,
            "updated_at": {"$gte": range_start},
            "$or": [{"case_type": "loan", "current_status": "disbursed"}, {"case_type": "insurance", "current_status": "policy_issued"}],
        }
    )
    async for doc in cursor:
        updated = doc.get("updated_at")
        if updated is None:
            continue
        updated_ist = to_ist(updated)
        key = (updated_ist.year, updated_ist.month)
        if key not in totals:
            continue
        if doc.get("case_type") == "loan":
            totals[key] += (doc.get("loan_details") or {}).get("offered_amount") or 0
        else:
            totals[key] += (doc.get("insurance_details") or {}).get("premium_amount") or 0

    items = [{"label": f"{yy}-{mm:02d}", "value": round(totals[(yy, mm)], 2)} for yy, mm in months]
    return {"available": True, "items": items}


WIDGET_PROVIDERS: dict[str, WidgetProvider] = {
    "today_leads": _today_leads,
    # Pending Follow-ups needs a follow-up/reminder date field on Lead (Module 6A,
    # frozen, has none) — a distinct concept from 6D's re-eligibility/task reminders,
    # so this stays an honest placeholder rather than being repurposed.
    "pending_followups": _not_yet_available,
    "pending_documents": _not_yet_available,
    "assigned_leads": _assigned_leads,
    "disbursed": _disbursed,
    "rejected": _rejected,
    "revenue": _not_yet_available,
    "tasks": _tasks,
    "notifications": _notifications,
    "recent_activities": _recent_activities,
    "department_summary": _department_summary,
    "employee_summary": _employee_summary,
    "referral_summary": _referral_summary,
    # Phase 4 additions — see docs/roadmap/TODO.md Phase 4 report for the full
    # permission-to-widget mapping.
    "total_leads": _total_leads,
    "customers_summary": _customers_summary,
    "applications_summary": _applications_summary,
    "applications_submitted": _applications_submitted,
    "loan_cases_total": _loan_cases_total,
    "insurance_cases_total": _insurance_cases_total,
    "policies_issued": _policies_issued,
    "insurance_rejected": _insurance_rejected,
    "loan_re_eligible": _loan_re_eligible,
    "insurance_re_eligible": _insurance_re_eligible,
    "tasks_completed": _tasks_completed,
    "lead_conversion_rate": _lead_conversion_rate,
    "today_performance": _today_performance,
    "monthly_performance": _monthly_performance,
    "lead_source_chart": _lead_source_chart,
    "loan_pipeline_chart": _loan_pipeline_chart,
    "insurance_pipeline_chart": _insurance_pipeline_chart,
    "employee_performance_chart": _employee_performance_chart,
    "referral_pending_commission": _referral_pending_commission,
    "referral_paid_commission": _referral_paid_commission,
    "referral_performance_chart": _referral_performance_chart,
    "loan_revenue": _loan_revenue,
    "insurance_revenue": _insurance_revenue,
    "monthly_revenue": _monthly_revenue,
    "revenue_trend_chart": _revenue_trend_chart,
}


async def compute_widget_data(db: AsyncIOMotorDatabase[Any], user: User, widget_key: str) -> dict[str, Any]:
    provider = WIDGET_PROVIDERS.get(widget_key, _not_yet_available)
    return await provider(db, user)
