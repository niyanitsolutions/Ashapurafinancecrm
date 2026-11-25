# ruff: noqa: F811
"""Read-only correction contracts exercised on owned disposable Mongo databases."""

from datetime import timedelta

from app.features.leads.document_collection import (
    CollectionFilters,
    filter_options,
    grouped,
)
from app.features.search.service import search_records
from app.utils.datetime import utc_now
from bson import ObjectId
from test_invoice_mongo_integration import real_invoice_db  # noqa: F401
from test_unified_operations import seed_identity, seed_team


async def test_options_are_staff_sources_and_catalogue_labels_not_customer_roles(
    real_invoice_db,
):
    db = real_invoice_db
    owner, employees = await seed_team(db)
    customer, app = await seed_identity(db, "Current Customer")
    owner_id, employee_id = owner.require_id(), employees[0][0].require_id()
    employee_user = employees[0][1].require_id()
    await db.owner_profiles.insert_one(
        {"user_id": owner_id, "full_name": "Assigning Owner", "is_deleted": False}
    )
    await db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {
            "$set": {
                "assigned_by": owner_id,
                "assigned_to": employee_id,
                "submission_source": "customer_portal",
            }
        },
    )
    for index, assigner in enumerate([employee_user, app.user_id]):
        doc = app.model_dump(by_alias=True, exclude={"id"})
        doc.update(
            application_code=f"EXTRA-{index}",
            assigned_by=assigner,
            assigned_to=employee_id,
            submission_source="customer_portal",
            created_at=utc_now() + timedelta(seconds=index),
        )
        await db.applications.insert_one(doc)
    source = ObjectId()
    await db.lead_sources.insert_one(
        {
            "_id": source,
            "name": "Configured Website",
            "is_deleted": False,
            "status": "active",
        }
    )
    custom = "custom:" + str(ObjectId())
    await db.daily_followup_status_options.insert_one(
        {
            "company_id": "default",
            "value": custom,
            "name": "Awaiting Bank Documents",
            "is_active": False,
        }
    )
    await db.daily_follow_ups.insert_one(
        {
            "application_id": app.require_id(),
            "is_deleted": False,
            "assigned_to": employee_id,
            "status": custom,
        }
    )
    before = {
        name: await db[name].count_documents({})
        for name in [
            "customers",
            "applications",
            "audit_logs",
            "lead_sources",
            "daily_followup_status_options",
        ]
    }
    options = (await filter_options(db, owner)).data
    assert {"value": owner_id, "label": "Assigning Owner"} in options["assigned_by"]
    assert {"value": employee_user, "label": employees[0][0].display_name} in options[
        "assigned_by"
    ]
    assert app.user_id not in {o["value"] for o in options["assigned_by"]}
    assert {"value": str(source), "label": "Configured Website"} in options["source_id"]
    assert {
        "value": "submission:customer_portal",
        "label": "Customer Portal",
    } in options["source_id"]
    assert {"value": custom, "label": "Awaiting Bank Documents"} in options[
        "follow_up_status"
    ]
    assert "designation_id" not in options
    data = (
        await grouped(
            db,
            owner,
            CollectionFilters(
                customer_id=customer.require_id(),
                assigned_by=owner_id,
                source_id="submission:customer_portal",
                follow_up_status=custom,
            ),
            1,
            200,
            None,
        )
    ).data
    assert data["total"] == 1 and data["items"][0]["application_count"] == 1
    primary = data["items"][0]["primary"]
    assert (
        primary["application_code"] == app.application_code
        and primary["status"] == "submitted"
    )
    assert primary["assigned_to_name"] == employees[0][0].display_name
    assert (
        await grouped(
            db,
            employees[1][1],
            CollectionFilters(customer_id=customer.require_id()),
            1,
            200,
            None,
        )
    ).data["total"] == 0
    assert before == {name: await db[name].count_documents({}) for name in before}


async def test_search_projection_and_navigation_keep_identity_private(real_invoice_db):
    db = real_invoice_db
    owner, employees = await seed_team(db)
    customer, app = await seed_identity(db, "Readable Customer")
    await db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {"$set": {"assigned_to": employees[0][0].require_id()}},
    )
    await db.loan_products.insert_one(
        {"_id": ObjectId(app.product_id), "name": "Personal Loan"}
    )
    rows = await search_records(db, owner, app.application_code)
    record = next(row for row in rows if row["type"] == "application")
    assert (
        record["label"] == app.application_code
        and record["customer_name"] == "Readable Customer"
    )
    assert record["product_name"] == "Personal Loan" and record["status"] == "submitted"
    assert (
        record["route"]
        == f"/applications/{app.require_id()}?from=document-collection&customer_id={customer.require_id()}"
    )
    person = next(row for row in rows if row["type"] == "customer")
    assert (
        person["route"]
        == f"/leads/document-collection?customer_id={customer.require_id()}&expand={customer.require_id()}"
    )
    assert (
        person["customer_code"] == customer.customer_code
        and person["mobile"] == customer.mobile
    )
    assert all(
        not any(key.startswith(("pan_", "aadhaar_", "password")) for key in row)
        for row in rows
    )
    assert not await search_records(db, employees[1][1], app.application_code)
    assert not any(
        row["type"] == "employee"
        for row in await search_records(db, employees[0][1], "Team")
    )


async def test_exact_pan_search_stays_owner_only_without_backfill(real_invoice_db):
    from app.security.encryption import encrypt
    from app.shared.customer_identity import pan_search_digest

    db = real_invoice_db
    owner, employees = await seed_team(db)
    customer, app = await seed_identity(db, "Verified Name")
    await db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {"$set": {"assigned_to": employees[0][0].require_id()}},
    )
    pan = "ABCDE1234F"
    await db.customers.update_one(
        {"_id": ObjectId(customer.require_id())},
        {
            "$set": {
                "pan_number_encrypted": encrypt(pan),
                "pan_search_digest": pan_search_digest(pan),
            }
        },
    )
    assert await search_records(db, owner, pan)
    assert not await search_records(db, employees[0][1], pan)
    assert all(pan not in str(row) for row in await search_records(db, owner, pan))
