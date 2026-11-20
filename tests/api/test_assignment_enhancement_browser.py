# ruff: noqa: F811
"""Opt-in real local API/browser journey; no external services or production data."""

import asyncio
import json
import os
from pathlib import Path

import pytest
import uvicorn
from app.config.database import get_database
from app.features.auth.indexes import ensure_auth_indexes
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from app.features.leads.indexes import ensure_lead_indexes
from app.security.password import hash_password
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_leads import _lead_master_data
from test_unified_operations import make_lead, seed_identity, seed_team


@pytest.mark.skipif(os.environ.get("AFS_ASSIGNMENT_BROWSER") != "1", reason="Opt-in local browser")
async def test_assignment_bulk_ui_and_names_responsive(client, real_invoice_db):
    db = real_invoice_db
    await ensure_auth_indexes(db)
    await ensure_lead_indexes(db)
    owner, employees = await seed_team(db)
    await db.users.update_one({"_id": ObjectId(owner.require_id())}, {"$set": {"password_hash": hash_password("InitialPass1!")}})
    master = await _lead_master_data(db)
    await AutoAssignment(db).save(AssignmentSettings(enabled=True, employee_ids=[employees[0][0].require_id()]), owner)
    lead = await make_lead((db, owner, employees, master))
    customer, application = await seed_identity(db)
    await db.applications.update_one({"_id": ObjectId(application.require_id())}, {"$set": {"status": "draft", "form_data": {"full_name_as_per_pan_card": "Actual Applicant"}}})
    await db.application_form_definitions.update_one({"_id": ObjectId(application.form_definition_id)}, {"$set": {"fields": [{"key": "full_name_as_per_pan_card", "label": "Full Name (as per PAN Card)", "field_type": "text"}]}})
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18773, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve())
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        process = await asyncio.create_subprocess_exec(str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/assignment-enhancement-ui-check.mjs"), cwd=root,
            env={**os.environ, "AFS_ASSIGNMENT_FIXTURE": json.dumps({"lead_id": lead.require_id(), "app_id": application.require_id(), "employees": [e.require_id() for e, _ in employees]})},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), 240)
        assert process.returncode == 0, output.decode(errors="replace")
        assert await db.leads.count_documents({}) == 1 and await db.applications.count_documents({}) == 1
        assert (await db.customers.find_one({"_id": ObjectId(customer.require_id())}))["full_name"] == "Customer"  # display fallback has no write side effects
        assert (await AutoAssignment(db).settings())["sequence"] == 1
        print(output.decode(errors="replace"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
