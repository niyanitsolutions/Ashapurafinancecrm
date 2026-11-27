"""Batch-only application context. Financial data is read from existing Loan cases."""

from typing import Any

from bson import ObjectId


async def enrich(db: Any, rows: list[dict[str, Any]], actor: Any) -> None:
    actor_ids = {
        event["actor_id"]
        for row in rows
        for event in row.get("history", [])
        if ObjectId.is_valid(event.get("actor_id"))
    }
    if actor_ids:
        actor_names = {
            e["user_id"]: e["display_name"]
            async for e in db.employees.find(
                {"user_id": {"$in": list(actor_ids)}}, {"user_id": 1, "display_name": 1}
            )
        }
        actor_names.update(
            {
                o["user_id"]: o["full_name"]
                async for o in db.owner_profiles.find(
                    {"user_id": {"$in": list(actor_ids)}}, {"user_id": 1, "full_name": 1}
                )
            }
        )
        for row in rows:
            row["history"] = [
                {
                    **e,
                    "actor_name": actor_names.get(
                        e.get("actor_id"), "System" if not e.get("actor_id") else e["actor_id"]
                    ),
                }
                for e in row.get("history", [])
            ]
    ids = {r.get("application_id") for r in rows if ObjectId.is_valid(r.get("application_id"))}
    if not ids:
        return
    apps = {
        str(a["_id"]): a
        async for a in db.applications.find(
            {"_id": {"$in": [ObjectId(i) for i in ids]}, "is_deleted": False},
            {
                "application_code": 1,
                "customer_id": 1,
                "user_id": 1,
                "status": 1,
                "created_at": 1,
                "daily_followup_moved_at": 1,
                "form_data.email": 1,
            },
        )
    }
    cases = {
        a["application_id"]: a
        async for a in db.application_workflows.find(
            {"application_id": {"$in": list(ids)}, "case_type": "loan", "is_deleted": False},
            {
                "application_id": 1,
                "case_code": 1,
                "case_type": 1,
                "branch_id": 1,
                "department_id": 1,
                "current_status": 1,
                "loan_details": 1,
            },
        )
    }
    cids = {a["customer_id"] for a in apps.values() if ObjectId.is_valid(a.get("customer_id"))}
    customers = (
        {
            str(c["_id"]): c
            async for c in db.customers.find(
                {"_id": {"$in": [ObjectId(i) for i in cids]}, "is_deleted": False},
                {"customer_code": 1, "email": 1},
            )
        }
        if cids
        else {}
    )
    uids = {a["user_id"] for a in apps.values() if ObjectId.is_valid(a.get("user_id"))}
    users = (
        {
            str(u["_id"]): u
            async for u in db.users.find(
                {"_id": {"$in": [ObjectId(i) for i in uids]}, "is_deleted": False}, {"status": 1}
            )
        }
        if uids
        else {}
    )
    permission_cache: dict[Any, Any] = {}
    for row in rows:
        app = apps.get(str(row.get("application_id")))
        if not app or row.get("identity_state") == "manual_review":
            continue
        customer = customers.get(app.get("customer_id"), {})
        case = cases.get(row.get("application_id"), {})
        if case:
            from app.core.exceptions import ForbiddenError
            from app.features.daily_operations.handover import permit

            try:
                await permit(db, actor, "application_workflows", case, "view", permission_cache)
            except ForbiddenError:
                case = {}
        details = case.get("loan_details") or {}
        row.update(
            application_code=app.get("application_code"),
            customer_code=customer.get("customer_code"),
            email=customer.get("email") or (app.get("form_data") or {}).get("email"),
            application_status=app.get("status"),
            account_status=users.get(app.get("user_id"), {}).get("status"),
            application_created_at=app.get("created_at"),
            movement_status="Moved to Daily Follow-up"
            if app.get("daily_followup_moved_at")
            else "Linked workspace",
            linked_case_id=str(case["_id"]) if case else row.get("case_id"),
            case_status=case.get("current_status"),
            approved_amount=details.get("offered_amount"),
            disbursed_amount=details.get("disbursed_amount"),
            disbursed_at=details.get("disbursed_at"),
            disbursement_remarks=details.get("disbursement_remarks"),
            top_up_period=details.get("top_up_period"),
            top_up_eligibility_date=details.get("top_up_eligibility_date"),
            top_up_remarks=details.get("top_up_remarks"),
        )
