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


@pytest.mark.skipif(
    os.environ.get("AFS_DC_CORRECTION_BROWSER") != "1", reason="Opt-in local browser"
)
async def test_document_collection_table_filters_and_search_responsive(
    client, real_invoice_db
):
    db = real_invoice_db
    await ensure_auth_indexes(db)
    await ensure_lead_indexes(db)
    owner, employees = await seed_team(db)
    await db.users.update_one(
        {"_id": ObjectId(owner.require_id())},
        {"$set": {"password_hash": hash_password("InitialPass1!")}},
    )
    master = await _lead_master_data(db)
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=[employees[0][0].require_id()]),
        owner,
    )
    lead = await make_lead((db, owner, employees, master))
    customer, application = await seed_identity(db, "Current Customer")
    await db.applications.update_one(
        {"_id": ObjectId(application.require_id())},
        {
            "$set": {
                "status": "draft",
                "form_data": {"full_name_as_per_pan_card": "Actual Applicant"},
            }
        },
    )
    await db.application_form_definitions.update_one(
        {"_id": ObjectId(application.form_definition_id)},
        {
            "$set": {
                "fields": [
                    {
                        "key": "full_name_as_per_pan_card",
                        "label": "Full Name (as per PAN Card)",
                        "field_type": "text",
                    }
                ]
            }
        },
    )
    await db.loan_products.insert_one(
        {
            "_id": ObjectId(application.product_id),
            "name": "Personal Loan",
            "is_deleted": False,
            "status": "active",
        }
    )
    await db.application_form_definitions.update_one(
        {"_id": ObjectId(application.form_definition_id)},
        {"$set": {"status": "active"}},
    )
    from app.features.owner.models import OwnerProfile

    profile = OwnerProfile(
        user_id=owner.require_id(),
        full_name="Assigning Owner",
        mobile=owner.mobile,
        email="owner@example.com",
    )
    await db.owner_profiles.insert_one(
        profile.model_dump(by_alias=True, exclude={"id"})
    )
    await db.applications.update_one(
        {"_id": ObjectId(application.require_id())},
        {
            "$set": {
                "assigned_by": owner.require_id(),
                "assigned_to": employees[0][0].require_id(),
                "submission_source": "customer_portal",
            }
        },
    )
    second_product = ObjectId()
    await db.loan_products.insert_one(
        {
            "_id": second_product,
            "name": "Home Loan",
            "is_deleted": False,
            "status": "active",
        }
    )
    form = await db.application_form_definitions.find_one(
        {"_id": ObjectId(application.form_definition_id)}
    )
    form.pop("_id")
    form["product_id"] = str(second_product)
    form_id = (await db.application_form_definitions.insert_one(form)).inserted_id
    second = await db.applications.find_one({"_id": ObjectId(application.require_id())})
    second.pop("_id")
    second.update(
        application_code="HOME-APPLICATION-2",
        product_id=str(second_product),
        form_definition_id=str(form_id),
        assigned_by=employees[0][1].require_id(),
    )
    await db.applications.insert_one(second)
    custom = "custom:" + str(ObjectId())
    await db.daily_followup_status_options.insert_one(
        {
            "company_id": "default",
            "value": custom,
            "name": "Awaiting documents",
            "is_active": True,
        }
    )
    await db.daily_follow_ups.insert_one(
        {
            "application_id": application.require_id(),
            "is_deleted": False,
            "status": custom,
            "assigned_to": employees[0][0].require_id(),
        }
    )
    from app.features.leads.document_collection import filter_options

    initial_options = (await filter_options(db, owner)).data
    assert any(
        option["label"] == "Assigning Owner"
        for option in initial_options["assigned_by"]
    ), initial_options["assigned_by"]
    original_apps = await db.applications.find({}).sort("_id", 1).to_list(10)
    original_customer = await db.customers.find_one(
        {"_id": ObjectId(customer.require_id())}
    )
    app = client._transport.app
    app.dependency_overrides[get_database] = lambda: db
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18773, log_level="error", lifespan="off"
        )
    )
    task = asyncio.create_task(server.serve())
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        process = await asyncio.create_subprocess_exec(
            str(root / "frontend/node_modules/.cache/voice-node22/node.exe"),
            str(root / "scripts/document-collection-correction-ui-check.mjs"),
            cwd=root,
            env={
                **os.environ,
                "AFS_ASSIGNMENT_FIXTURE": json.dumps(
                    {
                        "lead_id": lead.require_id(),
                        "owner_id": owner.require_id(),
                        "customer_id": customer.require_id(),
                        "mobile": customer.mobile,
                        "custom_status": custom,
                        "app_id": application.require_id(),
                        "employees": [e.require_id() for e, _ in employees],
                    }
                ),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 240)
        assert process.returncode == 0, output.decode(errors="replace")
        assert await db.leads.count_documents({}) == 1
        assert (
            await db.applications.find({}).sort("_id", 1).to_list(10) == original_apps
        )
        assert (
            await db.customers.find_one({"_id": ObjectId(customer.require_id())})
            == original_customer
        )
        assert await db.bin_entries.count_documents({}) == 0
        assert (await AutoAssignment(db).settings())["sequence"] == 1
        print(output.decode(errors="replace"))
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        server.should_exit = True
        await task
