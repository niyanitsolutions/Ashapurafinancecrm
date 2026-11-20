# ruff: noqa: F811
"""Real loopback Mongo checks; random disposable databases, no external providers."""

import asyncio

from app.features.daily_operations.catalog import install_catalog
from app.features.daily_operations.linked import OpenLinkedRequest, open_linked
from app.features.daily_operations.service import DailyOperationsService
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from app.features.leads.indexes import ensure_lead_indexes
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_leads import _lead_master_data
from test_unified_operations import make_lead, seed_team


async def test_real_standalone_rotation_duplicate_delivery_and_linked_workspace(
    real_invoice_db,
):
    db = real_invoice_db
    await ensure_lead_indexes(db)
    await install_catalog(db)
    owner, employees = await seed_team(db)
    master = await _lead_master_data(db)
    team = db, owner, employees, master
    service = AutoAssignment(db)
    pool = [e.require_id() for e, _ in employees]
    await service.save(AssignmentSettings(enabled=True, employee_ids=pool), owner)
    await asyncio.gather(*(make_lead(team, i) for i in range(18)))
    rows = await db.leads.find({}).sort("assignment_sequence", 1).to_list(30)
    assert [r["assignment_sequence"] for r in rows] == list(range(1, 19))
    assert [r["assigned_to"] for r in rows] == pool * 6
    delivered = await asyncio.gather(
        *(
            make_lead(team, 50, intake_key="same-synthetic-meta-delivery")
            for _ in range(8)
        )
    )
    assert len({lead.require_id() for lead in delivered}) == 1
    lead_id = delivered[0].require_id()
    daily = DailyOperationsService(db)
    working = await asyncio.gather(
        *(
            open_linked(
                daily, OpenLinkedRequest(entity="lead", record_id=lead_id), owner
            )
            for _ in range(8)
        )
    )
    assert len({row["id"] for row in working}) == 1
    assert await db.leads.count_documents({}) == 19
    assert await db.daily_follow_ups.count_documents({}) == 1
    assert len(working[0]["history"]) == 1
    # New instance models worker restart; replaying the outbox does not duplicate inbox/audit.
    row = await db.leads.find_one({"_id": ObjectId(lead_id)})
    event = {
        "employee_id": row["assigned_to"],
        "sequence": row["assignment_sequence"],
        "actor_id": owner.require_id(),
        "at": row["assigned_at"],
    }
    await db.leads.update_one(
        {"_id": row["_id"]}, {"$set": {"assignment_event_pending": event}}
    )
    await AutoAssignment(db).recover()
    assert (
        await db.notifications.count_documents({"notification_type": "lead_assigned"})
        == 19
    )
    assert (
        await db.audit_logs.count_documents({"event_type": "crm_auto_assigned"}) == 19
    )


async def test_real_owner_pending_queue_union_and_history(real_invoice_db, mock_redis):
    from app.features.leads.assignment_routes import history, pending

    db = real_invoice_db
    await ensure_lead_indexes(db)
    owner, employees = await seed_team(db)
    master = await _lead_master_data(db)
    lead = await make_lead((db, owner, employees, master))
    result = await pending(db, owner, 1)
    assert result.data["total"] == 1
    assert result.data["items"][0]["id"] == lead.require_id()
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=[employees[0][0].require_id()]),
        owner,
    )
    await AutoAssignment(db).assign("leads", lead.require_id(), owner)
    assert (await pending(db, owner, 1)).data["total"] == 0
    assert (await history(db, owner, 1)).data["total"] == 1


async def test_real_relationship_preflight_reports_without_modifying_records(
    real_invoice_db,
):
    from app.features.leads.reconciliation import assess_relationships

    db = real_invoice_db
    customer_id = ObjectId()
    await db.customers.insert_one(
        {
            "_id": customer_id,
            "user_id": str(ObjectId()),
            "full_name": "Customer",
            "is_deleted": False,
        }
    )
    app_id = (
        await db.applications.insert_one(
            {
                "user_id": str(ObjectId()),
                "customer_id": str(customer_id),
                "lead_id": None,
                "is_deleted": False,
                "creation_key": "legacy-repeated",
            }
        )
    ).inserted_id
    await db.applications.insert_one(
        {
            "user_id": str(ObjectId()),
            "customer_id": None,
            "lead_id": str(ObjectId()),
            "is_deleted": False,
            "creation_key": "legacy-repeated",
        }
    )
    before = await db.applications.find({}).sort("_id", 1).to_list(10)
    result = await assess_relationships(db)
    assert result["changes_applied"] == 0
    assert result["duplicate_keys"]["applications.creation_key"] == 1
    assert result["counts"]["placeholder_profiles"] == 1
    assert any(
        issue["record_id"] == str(app_id)
        and issue["kind"] == "application_customer_account_mismatch"
        for issue in result["issues"]
    )
    assert await db.applications.find({}).sort("_id", 1).to_list(10) == before
    import json
    from pathlib import Path

    output = (
        Path(__file__).resolve().parents[2]
        / "docs/screenshots/unified-crm-2026-11-19/preflight-synthetic.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "dataset": "Synthetic inconsistent records in a disposable loopback Mongo database",
                **result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
