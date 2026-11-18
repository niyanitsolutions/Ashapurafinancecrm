"""Unified portal requests preserve identity, ownership and existing staff workflows."""

import asyncio
from uuid import uuid4

import pytest
from app.features.customer.indexes import ensure_customer_indexes
from app.features.workflow_engine.indexes import ensure_workflow_engine_indexes
from bson import ObjectId
from test_customer import _seed_product_and_form
from test_document_collection_lifecycle import _register_customer, _upload_and_confirm
from test_workflow import _seed_workflow_definitions


@pytest.fixture
async def portal(client, mock_db, owner_headers):
    await ensure_customer_indexes(mock_db)
    await ensure_workflow_engine_indexes(mock_db)
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    customer = await _register_customer(client, "9000000098")
    r = await client.post("/api/v1/customers/me", headers=customer, json={"full_name": "Portal Customer"})
    assert r.status_code == 200, r.text
    return client, mock_db, owner_headers, customer, product


async def start(portal, request_key=None):
    client, _, _, customer, product = portal
    body = {"product_category": "loan", "product_id": product["product_id"]}
    if request_key:
        body["request_key"] = request_key
    r = await client.post("/api/v1/applications", headers=customer, json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def ready(portal):
    client, _, _, customer, product = portal
    app = await start(portal, str(uuid4()))
    r = await client.patch(f"/api/v1/applications/{app['id']}", headers=customer, json={"form_data": {"loan_amount": 50000}})
    assert r.status_code == 200, r.text
    await _upload_and_confirm(client, customer, app["id"], product["document_type_id"])
    return app


async def test_keyed_start_retries_and_parallel_requests_return_same_application(portal):
    _, db, _, _, _ = portal
    key = str(uuid4())
    apps = await asyncio.gather(*(start(portal, key) for _ in range(4)))
    assert len({app["id"] for app in apps}) == 1
    assert await db.applications.count_documents({}) == 1
    assert apps[0]["submission_source"] == "customer_portal"
    assert apps[0]["last_customer_activity_at"]
    # A deliberately new application remains allowed under the existing product rules.
    assert (await start(portal, str(uuid4())))["id"] != apps[0]["id"]


async def test_submit_is_idempotent_has_one_case_and_audit_and_preserves_timestamp(portal):
    client, db, _, customer, _ = portal
    app = await ready(portal)
    url = f"/api/v1/applications/{app['id']}/submit"
    results = await asyncio.gather(*(client.post(url, headers=customer, json={}) for _ in range(3)))
    assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
    stamps = {r.json()["data"]["submitted_at"] for r in results}
    assert len(stamps) == 1
    assert await db.applications.count_documents({}) == 1
    assert await db.application_workflows.count_documents({"application_id": app["id"]}) == 1
    assert await db.audit_logs.count_documents({"event_type": "application_submitted", "metadata.application_id": app["id"]}) == 1
    edit = await client.patch(f"/api/v1/applications/{app['id']}", headers=customer, json={"form_data": {"loan_amount": 1}})
    assert edit.status_code == 409
    stored = await db.applications.find_one({"_id": ObjectId(app["id"])})
    assert stored["form_data"]["loan_amount"] == 50000


async def test_customer_submission_visible_in_document_collection_with_metadata(portal):
    client, db, owner, customer, _ = portal
    app = await ready(portal)
    await client.post(f"/api/v1/applications/{app['id']}/submit", headers=customer, json={})
    rows = await client.get("/api/v1/leads?stage=document_collection", headers=owner)
    assert rows.status_code == 200, rows.text
    row = next(row for row in rows.json()["data"] if row["application_id"] == app["id"])
    assert row["is_lead_less"] and row["submission_source"] == "customer_portal"
    assert row["submitted_at"] and row["last_customer_activity_at"]
    assert await db.leads.count_documents({}) == 0  # No synthetic real Lead identity.


async def test_request_key_and_document_ownership_do_not_cross_customers(portal):
    client, db, _, _customer, product = portal
    key = str(uuid4())
    first = await start(portal, key)
    other = await _register_customer(client, "9000000097")
    await client.post("/api/v1/customers/me", headers=other, json={"full_name": "Other Customer"})
    r = await client.post("/api/v1/applications", headers=other, json={"product_category": "loan", "product_id": product["product_id"], "request_key": key})
    assert r.status_code == 200 and r.json()["data"]["id"] != first["id"]
    for suffix in ["", "/documents", f"/documents/{product['document_type_id']}/history"]:
        r = await client.get(f"/api/v1/applications/{first['id']}{suffix}", headers=other)
        assert r.status_code == 403
    r = await client.post(f"/api/v1/applications/{first['id']}/submit", headers=other, json={})
    assert r.status_code == 403
    assert await db.application_workflows.count_documents({}) == 0


async def test_legacy_missing_metadata_is_not_invented(portal):
    client, db, _, customer, _ = portal
    app = await start(portal)
    await db.applications.update_one({"_id": ObjectId(app["id"])}, {"$unset": {"submission_source": "", "last_customer_activity_at": "", "creation_key": ""}})
    r = await client.get(f"/api/v1/applications/{app['id']}", headers=customer)
    assert r.status_code == 200
    assert r.json()["data"]["submission_source"] == "unknown"
    assert r.json()["data"]["last_customer_activity_at"] is None


async def test_insurance_customer_submission_is_observable_without_moving_staff_cases(portal):
    from app.features.customer.models import Application
    from app.features.system_settings.models import InsuranceProduct
    from app.features.workflow_engine.models import ApplicationWorkflow
    from app.utils.datetime import utc_now

    client, db, owner, _, _ = portal
    customer = await db.customers.find_one({"mobile": "9000000098"})
    product = InsuranceProduct(name="Portal Insurance")
    pid = str((await db.insurance_products.insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    form = await db.application_form_definitions.find_one({})
    ids = {}
    for source in ["customer_portal", "staff_assisted", "unknown"]:
        app = Application(application_code="AFS-APP-" + source, user_id=customer["user_id"],
            customer_id=str(customer["_id"]), product_category="insurance", product_id=pid,
            form_definition_id=str(form["_id"]), status="submitted", submitted_at=utc_now(), submission_source=source)
        ids[source] = str((await db.applications.insert_one(app.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    url = "/api/v1/leads?stage=document_collection&product_category=insurance"
    response = await client.get(url, headers=owner)
    assert response.status_code == 200, response.text
    assert [row["application_id"] for row in response.json()["data"]] == [ids["customer_portal"]]
    case = ApplicationWorkflow(case_code="AFS-INS-FIXTURE", case_type="insurance", application_id=ids["customer_portal"],
        customer_id=str(customer["_id"]), product_category="insurance", product_id=pid, current_status="policy_document")
    await db.application_workflows.insert_one(case.model_dump(by_alias=True, exclude={"id"}))
    assert (await client.get(url, headers=owner)).json()["data"] == []
    assert (await db.application_workflows.find_one({"application_id": ids["customer_portal"]}))["current_status"] == "policy_document"


async def test_dashboard_totals_are_not_limited_by_application_list_and_hide_session_noise(portal):
    from app.shared.audit_log import AuditLog

    client, db, _, customer, _ = portal
    app = await start(portal)
    original = await db.applications.find_one({"_id": ObjectId(app["id"])})
    copies = []
    for index in range(201):
        copy = {key: value for key, value in original.items() if key not in {"_id", "creation_key"}}
        copy["application_code"] = f"AFS-APP-HISTORY-{index}"
        copies.append(copy)
    await db.applications.insert_many(copies)
    await db.audit_logs.insert_one(AuditLog(event_type="refresh_token", user_id=original["user_id"]).model_dump(by_alias=True, exclude={"id"}))
    response = await client.get("/api/v1/customers/me/dashboard", headers=customer)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["application_counts"] == {"all": 202, "draft": 202, "submitted": 0}
    assert all(event["event_type"] != "refresh_token" for event in data["recent_activity"])
