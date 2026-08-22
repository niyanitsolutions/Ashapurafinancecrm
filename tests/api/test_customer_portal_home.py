"""Final Phase — regression coverage for Phase 5/5.1's Customer Portal Home endpoints
(`GET /customers/me/dashboard`, `GET /applications/{id}/timeline`, `GET
/customers/me/messages`, `POST /customers/me/support-requests`). These shipped without
their own pytest coverage (verified only via ad-hoc scratch scripts during development)
— this file gives them permanent regression protection, including the customer-scoping
boundary on Messages, which is a real security property (a customer must never see
another customer's communication history).
"""

from datetime import UTC, datetime

from app.features.leads.constants import LeadActivityType
from app.features.leads.models import Lead, LeadActivity
from app.utils.helpers import to_object_id
from test_customer import _create_employee, _create_lead_doc, _seed_product_and_form, _seed_workflow_definitions, _signup_via_otp


async def _register_customer(client, mock_db, *, mobile: str) -> dict:
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, mobile, dev_otp)
    r = await client.post("/api/v1/customers/me", json={"full_name": "Vijay Kumar", "email": "vijay@example.com"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers


async def test_dashboard_no_application(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9611111111")
    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["has_application"] is False
    assert data["relationship_manager"] is None
    assert data["document_groups"] == []


async def test_dashboard_with_draft_application_shows_progress_and_documents(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111112")

    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]

    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["has_application"] is True
    assert data["application_id"] == application_id
    assert data["status_label"] == "Draft"
    assert data["progress_percent"] == 0  # loan_amount not filled in yet
    assert data["pending_documents_count"] == 1
    assert len(data["document_groups"]) == 1
    assert data["document_groups"][0]["documents"][0]["uploaded"] is False

    # Filling the one required field should move progress to 100%
    r = await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    assert r.json()["data"]["progress_percent"] == 100


async def test_dashboard_shows_relationship_manager_once_assigned(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111113")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]

    employee = await _create_employee(client, owner_headers, master_data, mobile="9511111199", email="rm@example.com")
    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    rm = r.json()["data"]["relationship_manager"]
    assert rm is not None
    assert rm["id"] == employee["id"]
    assert rm["email"] == "rm@example.com"


# ---------------------------------------------------------------------- production stabilization: RM assignment propagation


async def test_dashboard_shows_relationship_manager_seeded_from_pre_assigned_lead(client, mock_db, owner_headers, master_data):
    """Regression test for the "Relationship Manager: Not yet assigned" report. A Lead
    staff already assigned before the customer ever creates an Application must seed
    that Application's own `assigned_to` at creation time — the portal dashboard
    already resolved RM correctly from `Application.assigned_to`, the bug was that
    field starting null. Covers the direct-portal (Flow 2) `start_application` path."""
    product = await _seed_product_and_form(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9511111198", email="preassigned-rm@example.com")
    mobile = "9611111150"
    lead = Lead(
        lead_code="AFS-LEAD-PRE1", full_name="Pre Assigned", mobile=mobile, email="pre@example.com",
        source_id="000000000000000000000000", product_category=product["product_category"], product_id=product["product_id"],
        assigned_to=employee["id"],
    )
    await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))

    customer_headers = await _register_customer(client, mock_db, mobile=mobile)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    rm = r.json()["data"]["relationship_manager"]
    assert rm is not None
    assert rm["id"] == employee["id"]


async def test_dashboard_relationship_manager_not_seeded_when_no_matching_lead(client, mock_db, owner_headers):
    """No false positive: a customer with no matching pre-assigned Lead still starts
    unassigned, exactly as before this fix."""
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111151")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/customers/me/dashboard", headers=customer_headers)
    assert r.json()["data"]["relationship_manager"] is None


async def test_application_timeline_reflects_draft_then_submitted(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111114")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    assert r.status_code == 200, r.text
    entries = r.json()["data"]
    assert len(entries) == 1
    assert entries[0]["label"] == "Application Started"
    assert entries[0]["state"] == "current"

    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    r = await client.post(f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"}, headers=customer_headers)
    s3_key = r.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    entries = r.json()["data"]
    labels = [e["label"] for e in entries]
    # Submission also creates the Application's Loan Case (lazy get-or-create, Module 6C)
    # — get_application_timeline appends one entry per seeded WorkflowDefinition for that
    # case_type after "Application Submitted" (see customer/service.py's own docstring on
    # get_application_timeline). This test file only seeds the case's first stage
    # (loan:new_customer, via _seed_workflow_definitions), so exactly one such entry
    # appears here, and it's the case's current stage — "current", not "completed".
    assert labels == ["Application Started", "Application Submitted", "New Customer"]
    assert [e["state"] for e in entries] == ["completed", "completed", "current"]


async def test_application_timeline_shows_owner_self_assigned_lead(client, mock_db, owner_headers):
    """Production bug fix: `_build_lead_assigned_entry` used to look up the Lead's
    ASSIGNED activity's `employee_id` only against `employees`, so a lead an Owner
    self-assigned (see LeadService._assign — an Owner has no Employee record by design)
    silently disappeared from this timeline entirely instead of showing "Assigned to
    Owner"."""
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111120")

    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]

    owner_user = await mock_db["users"].find_one({"mobile": "9000000001"})
    owner_user_id = str(owner_user["_id"])
    lead_id = await _create_lead_doc(mock_db, product, mobile="9611111120", full_name="Owner Self Assigned Lead")
    activity = LeadActivity(lead_id=lead_id, event_type=LeadActivityType.ASSIGNED, metadata={"employee_id": owner_user_id})
    await mock_db["lead_activities"].insert_one(activity.model_dump(by_alias=True, exclude={"id"}))
    await mock_db["applications"].update_one({"_id": to_object_id(application_id)}, {"$set": {"lead_id": lead_id}})

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    assert r.status_code == 200, r.text
    labels = [e["label"] for e in r.json()["data"]]
    assert "Lead Created" in labels
    assert "Assigned to Owner" in labels


async def test_support_request_creates_task_for_assigned_relationship_manager(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9611111115")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]
    employee = await _create_employee(client, owner_headers, master_data, mobile="9511111198", email="rm2@example.com")
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.post(
        "/api/v1/customers/me/support-requests", json={"subject": "Need help", "message": "Please call me back"}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created_task"] is True

    tasks = await mock_db["tasks"].find({}).to_list(length=10)
    assert len(tasks) == 1
    assert tasks[0]["assigned_to"] == employee["id"]
    assert "Need help" in tasks[0]["title"]


async def test_support_request_notifies_owner_when_no_relationship_manager(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9611111116")

    r = await client.post(
        "/api/v1/customers/me/support-requests", json={"subject": "Urgent", "message": "No RM assigned yet"}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created_task"] is False

    tasks = await mock_db["tasks"].find({}).to_list(length=10)
    assert len(tasks) == 0  # never fakes a Task assignment when no Employee exists to own it

    notifications = await mock_db["notifications"].find({"notification_type": "support_request_raised"}).to_list(length=10)
    assert len(notifications) == 1
    assert notifications[0]["title"] == "Support request: Urgent"


async def test_messages_are_scoped_to_the_calling_customer_only(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9611111117")
    other_customer_headers = await _register_customer(client, mock_db, mobile="9611111118")

    # One message for each customer, matched by recipient mobile — never by a shared
    # collection scan without a filter.
    for mobile in ("9611111117", "9611111118"):
        queue_id = (await mock_db["communication_queue"].insert_one(
            {"channel": "sms", "recipient": mobile, "template_id": "x", "variables": {}, "rendered_body": f"Hello {mobile}", "status": "sent"}
        )).inserted_id
        await mock_db["communication_history"].insert_one({
            "queue_item_id": str(queue_id), "channel": "sms", "provider": "test", "recipient": mobile,
            "template_id": "x", "template_name": "Greeting", "variables": {}, "status": "sent", "retry_count": 0,
            "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC), "is_deleted": False,
        })

    r = await client.get("/api/v1/customers/me/messages", headers=customer_headers)
    assert r.status_code == 200, r.text
    messages = r.json()["data"]
    assert len(messages) == 1
    assert messages[0]["body"] == "Hello 9611111117"
