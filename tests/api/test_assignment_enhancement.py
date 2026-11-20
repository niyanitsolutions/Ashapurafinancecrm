# ruff: noqa: F811
"""Synthetic API regression tests for previewed assignment and seeded applicant names."""

import pytest
from app.features.leads.auto_assignment import AssignmentSettings, AutoAssignment
from app.features.leads.service import LeadService
from bson import ObjectId
from test_leads import _login
from test_portal_modernisation import portal, start  # noqa: F401
from test_unified_operations import make_lead, seed_identity, team  # noqa: F401


async def call_bulk(client, headers, path, ids, employee, *, reassign=False):
    body = {"ids": ids, "employee_id": employee, "allow_reassignment": reassign}
    preview = await client.post(path, headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    result = await client.post(
        path,
        headers=headers,
        json={**body, "preview_id": preview.json()["data"]["preview_id"]},
    )
    assert result.status_code == 200, result.text
    return (
        preview.json()["data"],
        result.json()["data"],
        {**body, "preview_id": preview.json()["data"]["preview_id"]},
    )


async def test_bulk_fresh_partial_preview_commit_idempotency_and_stage(
    team, client, owner_headers
):
    db, _, employees, _ = team
    first, second = await make_lead(team, 1), await make_lead(team, 2)
    original = await db.leads.find_one({"_id": ObjectId(first.require_id())})
    preview, result, body = await call_bulk(
        client,
        owner_headers,
        "/api/v1/leads/bulk-assign",
        [first.require_id(), second.require_id(), "bad-id"],
        employees[0][0].require_id(),
    )
    assert preview["eligible"] == 2 and preview["failed"] == 1
    assert result["assigned"] == 2 and result["failed"] == 1
    row = await db.leads.find_one({"_id": original["_id"]})
    assert (
        row["stage"] == "fresh" and row["assigned_to"] == employees[0][0].require_id()
    )
    assert row["mobile"] == original["mobile"] and row["email"] == original["email"]
    again = await client.post(
        "/api/v1/leads/bulk-assign", headers=owner_headers, json=body
    )
    assert again.json()["data"]["assigned"] == 2
    assert await db.audit_logs.count_documents({"event_type": "crm_bulk_assigned"}) == 2
    assert await db.leads.count_documents({}) == 2


async def test_bulk_does_not_replace_owners_without_confirmation(
    team, client, owner_headers
):
    db, owner, employees, _ = team
    lead = await make_lead(team)
    await LeadService(db).assign_lead(
        lead.require_id(), employees[0][0].require_id(), owner
    )
    # Assigned-stage records are excluded from Fresh bulk, irrespective of confirmation.
    preview, result, _ = await call_bulk(
        client,
        owner_headers,
        "/api/v1/leads/bulk-assign",
        [lead.require_id()],
        employees[1][0].require_id(),
    )
    assert preview["skipped"] == result["skipped"] == 1
    await db.leads.update_one(
        {"_id": ObjectId(lead.require_id())}, {"$set": {"stage": "fresh"}}
    )
    _, result, _ = await call_bulk(
        client,
        owner_headers,
        "/api/v1/leads/bulk-assign",
        [lead.require_id()],
        employees[1][0].require_id(),
    )
    assert result["skipped"] == 1
    _, result, _ = await call_bulk(
        client,
        owner_headers,
        "/api/v1/leads/bulk-assign",
        [lead.require_id()],
        employees[1][0].require_id(),
        reassign=True,
    )
    assert result["assigned"] == 1


async def test_preview_revalidates_owner_and_employee_changes(
    team, client, owner_headers
):
    db, owner, employees, _ = team
    lead = await make_lead(team)
    body = {"ids": [lead.require_id()], "employee_id": employees[0][0].require_id()}
    preview = (
        await client.post("/api/v1/leads/bulk-assign", headers=owner_headers, json=body)
    ).json()["data"]
    await db.users.update_one(
        {"_id": ObjectId(employees[0][1].require_id())},
        {"$set": {"status": "inactive"}},
    )
    result = (
        await client.post(
            "/api/v1/leads/bulk-assign",
            headers=owner_headers,
            json={**body, "preview_id": preview["preview_id"]},
        )
    ).json()["data"]
    assert result["failed"] == 1 and not result["assigned"]
    assert (await LeadService(db).get_lead(lead.require_id())).assigned_to is None
    await LeadService(db).assign_lead(
        lead.require_id(), employees[1][0].require_id(), owner
    )
    retry = (
        await client.post(
            "/api/v1/leads/bulk-assign",
            headers=owner_headers,
            json={**body, "preview_id": preview["preview_id"]},
        )
    ).json()["data"]
    assert retry["skipped"] == 1


async def test_empty_and_unauthorized_bulk_rejected(team, client, owner_headers):
    _, _, employees, _ = team
    employee = employees[0][0].require_id()
    assert (
        await client.post(
            "/api/v1/leads/bulk-assign",
            headers=owner_headers,
            json={"ids": [], "employee_id": employee},
        )
    ).status_code == 422
    headers = await _login(client, employees[0][1].mobile)
    for path in ("/api/v1/leads/bulk-assign", "/api/v1/applications/bulk-assign"):
        assert (
            await client.post(
                path,
                headers=headers,
                json={"ids": [str(ObjectId())], "employee_id": employee},
            )
        ).status_code == 403


async def test_historical_retry_requires_explicit_preview_and_skips_rejected(
    team, client, owner_headers
):
    db, owner, employees, _ = team
    good, rejected = await make_lead(team, 1), await make_lead(team, 2)
    await db.leads.update_many({}, {"$unset": {"auto_assignment_eligible": ""}})
    await db.leads.update_one(
        {"_id": ObjectId(rejected.require_id())}, {"$set": {"stage": "rejected"}}
    )
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=[employees[0][0].require_id()]),
        owner,
    )
    records = [{"collection": "leads", "id": r.require_id()} for r in (good, rejected)]
    preview = (
        await client.post(
            "/api/v1/leads/auto-assignment/bulk-retry",
            headers=owner_headers,
            json={"records": records},
        )
    ).json()["data"]
    assert (await LeadService(db).get_lead(good.require_id())).assigned_to is None
    assert preview["eligible"] == 1 and preview["skipped"] == 1
    result = (
        await client.post(
            "/api/v1/leads/auto-assignment/bulk-retry",
            headers=owner_headers,
            json={"records": records, "preview_id": preview["preview_id"]},
        )
    ).json()["data"]
    assert result["assigned"] == 1 and result["skipped"] == 1
    assert (await LeadService(db).get_lead(rejected.require_id())).assigned_to is None


@pytest.mark.parametrize(
    "key", ["full_name_as_per_pan_card", "applicant_name_as_per_pan_card"]
)
async def test_document_collection_resolves_shipped_schema_and_preserves_contacts(
    mock_db, client, owner_headers, key
):
    customer, application = await seed_identity(mock_db)
    await mock_db.application_form_definitions.update_one(
        {"_id": ObjectId(application.form_definition_id)},
        {
            "$set": {
                "fields": [{"key": key, "label": "Applicant", "field_type": "text"}]
            }
        },
    )
    await mock_db.applications.update_one(
        {"_id": ObjectId(application.require_id())},
        {"$set": {"status": "draft", "form_data": {key: "Actual Applicant"}}},
    )
    before = await mock_db.customers.find_one({"_id": ObjectId(customer.require_id())})
    response = await client.get(
        "/api/v1/leads?stage=document_collection", headers=owner_headers
    )
    assert response.status_code == 200, response.text
    row = next(
        r
        for r in response.json()["data"]
        if r["application_id"] == application.require_id()
    )
    assert row["full_name"] == "Actual Applicant" and row["mobile"] == customer.mobile
    assert (
        await mock_db.customers.find_one({"_id": before["_id"]}) == before
    )  # list is read-only
    await mock_db.customers.update_one(
        {"_id": before["_id"]}, {"$set": {"full_name": "Established Name"}}
    )
    assert (
        await client.get(
            "/api/v1/leads?stage=document_collection", headers=owner_headers
        )
    ).json()["data"][0]["full_name"] == "Established Name"


async def test_document_collection_missing_relationship_uses_clear_fallback(
    mock_db, client, owner_headers
):
    _, app = await seed_identity(mock_db)
    await mock_db.applications.update_one(
        {"_id": ObjectId(app.require_id())},
        {"$set": {"customer_id": "invalid-id", "form_data": {}}},
    )
    response = await client.get(
        "/api/v1/leads?stage=document_collection", headers=owner_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"][0]["full_name"] == "Name unavailable"


async def test_mismatched_profile_does_not_expose_another_customers_contacts(mock_db, client, owner_headers):
    from app.features.customer.models import Customer

    _, app = await seed_identity(mock_db)
    other = Customer(customer_code="OTHER", user_id=str(ObjectId()), full_name="Different Person", mobile="9000069999", email="different@example.com")
    oid = (await mock_db.customers.insert_one(other.model_dump(exclude={"id"}))).inserted_id
    await mock_db.applications.update_one({"_id": ObjectId(app.require_id())}, {"$set": {"customer_id": str(oid)}})
    response = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert response.status_code == 200, response.text
    row = response.json()["data"][0]
    assert row["full_name"] == "Ramesh Test"
    assert row["mobile"] == "" and row["email"] is None


async def test_bulk_applications_preserves_identity_documents_and_stage(
    team, client, owner_headers
):
    db, _, employees, _ = team
    customer, app = await seed_identity(db)
    await db.application_documents.insert_one(
        {"application_id": app.require_id(), "version": 3, "is_deleted": False}
    )
    preview, result, _ = await call_bulk(
        client,
        owner_headers,
        "/api/v1/applications/bulk-assign",
        [app.require_id()],
        employees[0][0].require_id(),
    )
    assert preview["eligible"] == result["assigned"] == 1
    row = await db.applications.find_one({"_id": ObjectId(app.require_id())})
    assert row["customer_id"] == customer.require_id() and row["status"] == "submitted"
    assert (
        await db.application_documents.count_documents(
            {"application_id": app.require_id(), "version": 3}
        )
        == 1
    )
    assert await db.applications.count_documents({}) == 1


async def test_draft_document_collection_and_fresh_share_rotation_across_restarts(
    portal,
):
    from test_leads import _lead_master_data
    from test_unified_operations import seed_team

    _, db, _, _, _ = portal
    owner, employees = await seed_team(db)
    team = db, owner, employees, await _lead_master_data(db)
    pool = [e.require_id() for e, _ in employees]
    await AutoAssignment(db).save(
        AssignmentSettings(enabled=True, employee_ids=pool), owner
    )
    first = await start(portal)
    second = await start(portal)
    fresh = await make_lead(team)
    assert first["status"] == "draft" and first["assigned_to"] == pool[0]
    assert second["assigned_to"] == pool[1] and fresh.assigned_to == pool[2]
    assert (await AutoAssignment(db).settings())["sequence"] == 3
    await AutoAssignment(db).assign("applications", first["id"], owner, source="retry")
    assert (await AutoAssignment(db).settings())["sequence"] == 3


async def test_effective_denial_skips_employee_for_auto_and_bulk(
    team, client, owner_headers
):
    db, owner, employees, _ = team
    role = await db.employee_roles.find_one(
        {"employee_id": employees[0][0].require_id()}
    )
    permission = await db.permissions.find_one({"module": "leads", "resource": "leads"})
    await db.role_permissions.update_one(
        {"role_id": role["role_id"], "permission_id": str(permission["_id"])},
        {"$set": {"denied_actions": ["view"]}},
    )
    await AutoAssignment(db).save(
        AssignmentSettings(
            enabled=True, employee_ids=[e.require_id() for e, _ in employees[:2]]
        ),
        owner,
    )
    lead = await make_lead(team)
    assert lead.assigned_to == employees[1][0].require_id()
    preview = await client.post(
        "/api/v1/leads/bulk-assign",
        headers=owner_headers,
        json={
            "ids": [lead.require_id()],
            "employee_id": employees[0][0].require_id(),
            "allow_reassignment": True,
        },
    )
    assert preview.json()["data"]["failed"] == 1
