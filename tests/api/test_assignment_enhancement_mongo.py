# ruff: noqa: F811
"""Real standalone MongoDB race checks in an owned disposable database."""

import asyncio

from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from app.features.leads.bulk_assignment import execute, record_list
from app.features.leads.indexes import ensure_lead_indexes
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_leads import _lead_master_data
from test_unified_operations import make_lead, seed_team


async def test_real_bulk_preview_concurrent_confirmation_and_rotation_are_independent(real_invoice_db):
    db = real_invoice_db
    await ensure_lead_indexes(db)
    owner, employees = await seed_team(db)
    master = await _lead_master_data(db)
    pool = [e.require_id() for e, _ in employees]
    await AutoAssignment(db).save(AssignmentSettings(enabled=True, employee_ids=pool), owner)
    leads = await asyncio.gather(*(make_lead((db, owner, employees, master), i) for i in range(8)))
    records = record_list("leads", [lead.require_id() for lead in leads])
    selected = pool[1]
    preview = await execute(db, owner, records, selected, True, "bulk", None)
    await asyncio.gather(*(execute(db, owner, records, selected, True, "bulk", preview["preview_id"]) for _ in range(5)))
    assert await db.leads.count_documents({"assigned_to": selected}) == 8
    expected_events = preview["eligible"]  # Already-owned rows are skipped, never re-audited.
    assert await db.audit_logs.count_documents({"event_type": "crm_bulk_assigned"}) == expected_events
    assert await db.leads.count_documents({}) == 8
    assert (await AutoAssignment(db).settings())["sequence"] == 8
    assert not await db.leads.count_documents({"stage": {"$ne": "fresh"}})
    assert await db.assignment_previews.count_documents({"_id": ObjectId(preview["preview_id"])}) == 1
