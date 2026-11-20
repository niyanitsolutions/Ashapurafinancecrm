# ruff: noqa: F811
"""Real application submission pipeline with synthetic provider/storage fixtures."""

from app.features.customer.models import FormFieldDefinition
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from bson import ObjectId
from test_portal_modernisation import portal, ready  # noqa: F401
from test_unified_operations import seed_team


async def test_submitted_name_assignment_and_document_collection_keep_same_ids(portal):
    client, db, owner_headers, customer_headers, _ = portal
    owner, employees = await seed_team(db)
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=[employees[0][0].require_id()]),
        owner,
    )
    await db.customers.update_many({}, {"$set": {"full_name": "Customer"}})
    application = await ready(portal)
    field = FormFieldDefinition(key="full_name", label="Full name", field_type="text")
    await db.application_form_definitions.update_many(
        {}, {"$push": {"fields": field.model_dump()}}
    )
    patch = await client.patch(
        f"/api/v1/applications/{application['id']}",
        headers=customer_headers,
        json={"form_data": {"loan_amount": 50000, "full_name": "Ramesh Test"}},
    )
    assert patch.status_code == 200
    before = await db.applications.find_one({"_id": ObjectId(application["id"])})
    for _ in range(2):
        response = await client.post(
            f"/api/v1/applications/{application['id']}/submit",
            headers=customer_headers,
            json={},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["assigned_to"] == employees[0][0].require_id()
    after = await db.applications.find_one({"_id": before["_id"]})
    assert (
        after["customer_id"] == before["customer_id"] and after.get("lead_id") is None
    )
    customer = await db.customers.find_one({"_id": ObjectId(after["customer_id"])})
    assert (
        customer["full_name"] == "Ramesh Test" and len(customer["profile_history"]) == 1
    )
    case = await db.application_workflows.find_one(
        {"application_id": application["id"]}
    )
    assert case["assigned_to"] == after["assigned_to"]
    listing = await client.get(
        "/api/v1/leads?stage=document_collection", headers=owner_headers
    )
    assert listing.status_code == 200, listing.text
    row = next(
        row
        for row in listing.json()["data"]
        if row["application_id"] == application["id"]
    )
    assert row["full_name"] == "Ramesh Test" and row["stage"] == "document_collection"
    assert await db.leads.count_documents({}) == 0
    assert await db.applications.count_documents({}) == 1
    assert (await AutoAssignment(db).settings())["sequence"] == 1
    from app.features.daily_operations.catalog import install_catalog

    await install_catalog(db)
    working = await client.post(
        "/api/v1/daily-operations/linked-follow-up",
        headers=owner_headers,
        json={"entity": "application", "record_id": application["id"]},
    )
    assert working.status_code == 200, working.text
    assert working.json()["data"]["application_id"] == application["id"]
    assert working.json()["data"]["customer_name"] == "Ramesh Test"
