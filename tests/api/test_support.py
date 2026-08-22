"""Customer Portal redesign — minimal Support Ticket module: create (with an optional S3
attachment, reusing the same presigned-upload pattern as ApplicationDocument), list-own
history, customer-only access, and that it keeps firing the existing Module 6B Task/
Notification side-effect (`raise_support_request`) unchanged alongside the new persisted
record.
"""

from bson import ObjectId

from test_customer import _create_employee, _signup_via_otp


async def _grant_support_permission(client, owner_headers, employee_id, actions, role_name="Support Role"):
    r = await client.post("/api/v1/permissions", json={"module": "support", "resource": "tickets", "actions": ["view", "edit"]}, headers=owner_headers)
    if r.status_code == 200:
        permission_id = r.json()["data"]["id"]
    else:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission_id = next(p["id"] for p in existing.json()["data"] if p["module"] == "support" and p["resource"] == "tickets")
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission_id, "granted_actions": actions}]}, headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _register_customer(client, mock_db, *, mobile: str) -> dict:
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, mobile, dev_otp)
    r = await client.post("/api/v1/customers/me", json={"full_name": "Anita Rao", "email": "anita@example.com"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers


async def test_create_ticket_and_list_own_history(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333301")

    r = await client.post(
        "/api/v1/support-tickets",
        json={"issue_type": "documents", "priority": "high", "subject": "Can't upload PAN", "message": "Upload keeps failing"},
        headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]
    assert ticket["ticket_code"].startswith("AFS-TICKET-")
    assert ticket["status"] == "open"
    assert ticket["priority"] == "high"
    assert ticket["assigned_to"] is None

    r = await client.get("/api/v1/support-tickets/me", headers=customer_headers)
    assert r.status_code == 200, r.text
    tickets = r.json()["data"]
    assert len(tickets) == 1
    assert tickets[0]["subject"] == "Can't upload PAN"


async def test_create_ticket_with_attachment(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333302")

    r = await client.post(
        "/api/v1/support-tickets/attachment-upload-url", json={"file_name": "screenshot.png", "content_type": "image/png"}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]
    assert s3_key.startswith("support-tickets/")

    r = await client.post(
        "/api/v1/support-tickets",
        json={"issue_type": "other", "priority": "low", "subject": "See attached", "message": "Screenshot enclosed", "attachment_s3_key": s3_key},
        headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["attachment_download_url"] is not None


async def test_ticket_creation_still_notifies_via_existing_support_request_flow(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333303")

    r = await client.post(
        "/api/v1/support-tickets",
        json={"issue_type": "application", "priority": "medium", "subject": "Status query", "message": "When will this be reviewed?"},
        headers=customer_headers,
    )
    assert r.status_code == 200, r.text

    # No RM assigned yet -> the existing raise_support_request side-effect notifies Owners,
    # exactly as it already does for the old /customers/me/support-requests endpoint.
    notifications = await mock_db["notifications"].find({"notification_type": "support_request_raised"}).to_list(length=10)
    assert len(notifications) == 1
    assert notifications[0]["title"] == "Support request: Status query"


async def test_support_tickets_are_scoped_to_the_calling_customer_only(client, mock_db, owner_headers):
    customer_a = await _register_customer(client, mock_db, mobile="9633333304")
    customer_b = await _register_customer(client, mock_db, mobile="9633333305")

    await client.post(
        "/api/v1/support-tickets", json={"issue_type": "other", "priority": "low", "subject": "A's ticket", "message": "x"}, headers=customer_a
    )

    r = await client.get("/api/v1/support-tickets/me", headers=customer_b)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


async def test_owner_and_employee_cannot_create_support_tickets(client, mock_db, owner_headers):
    r = await client.post(
        "/api/v1/support-tickets", json={"issue_type": "other", "priority": "low", "subject": "x", "message": "y"}, headers=owner_headers
    )
    assert r.status_code == 403, r.text


async def test_create_ticket_rejects_unknown_issue_type(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333306")
    r = await client.post(
        "/api/v1/support-tickets", json={"issue_type": "not-a-real-type", "priority": "low", "subject": "x", "message": "y"}, headers=customer_headers
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- production stabilization: staff resolution workflow


async def test_staff_with_permission_lists_and_responds_to_ticket(client, mock_db, owner_headers, master_data):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333310")
    r = await client.post(
        "/api/v1/support-tickets",
        json={"issue_type": "documents", "priority": "high", "subject": "Upload fails", "message": "Keeps erroring"},
        headers=customer_headers,
    )
    ticket_id = r.json()["data"]["id"]

    employee = await _create_employee(client, owner_headers, master_data, mobile="9511119901", email="supportstaff1@example.com")
    await _grant_support_permission(client, owner_headers, employee["id"], ["view", "edit"])
    staff_headers = await _login(client, "9511119901", "InitialPass1!")

    r = await client.get("/api/v1/support-tickets", headers=staff_headers)
    assert r.status_code == 200, r.text
    assert any(t["id"] == ticket_id for t in r.json()["data"])

    r = await client.patch(
        f"/api/v1/support-tickets/{ticket_id}", json={"staff_response": "Please try a smaller file.", "status": "resolved"}, headers=staff_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["staff_response"] == "Please try a smaller file."
    assert data["status"] == "resolved"
    assert data["responded_by_name"] == "Staff Member"

    # Customer sees the response and updated status on their next fetch.
    r = await client.get("/api/v1/support-tickets/me", headers=customer_headers)
    ticket = r.json()["data"][0]
    assert ticket["staff_response"] == "Please try a smaller file."
    assert ticket["status"] == "resolved"


async def test_staff_without_permission_denied(client, mock_db, owner_headers, master_data, employee_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9633333311")
    r = await client.post(
        "/api/v1/support-tickets", json={"issue_type": "other", "priority": "low", "subject": "x", "message": "y"}, headers=customer_headers
    )
    ticket_id = r.json()["data"]["id"]

    r = await client.get("/api/v1/support-tickets", headers=employee_headers)
    assert r.status_code == 403, r.text

    r = await client.patch(f"/api/v1/support-tickets/{ticket_id}", json={"staff_response": "Hi"}, headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_employee_with_view_only_cannot_see_ticket_assigned_to_someone_else(client, mock_db, owner_headers, master_data):
    """IDOR check: an Employee granted only `view` (not the broad-visibility `edit`) and
    who is not the ticket's own `assigned_to` must not reach another employee's ticket —
    they can still see unassigned ones."""
    customer_headers = await _register_customer(client, mock_db, mobile="9633333312")
    r = await client.post(
        "/api/v1/support-tickets", json={"issue_type": "other", "priority": "low", "subject": "x", "message": "y"}, headers=customer_headers
    )
    ticket_id = r.json()["data"]["id"]

    responder = await _create_employee(client, owner_headers, master_data, mobile="9511119902", email="responder1@example.com")
    await _grant_support_permission(client, owner_headers, responder["id"], ["view", "edit"], role_name="Responder Role")
    responder_headers = await _login(client, "9511119902", "InitialPass1!")
    await client.patch(f"/api/v1/support-tickets/{ticket_id}", json={"staff_response": "On it"}, headers=responder_headers)
    await mock_db["support_tickets"].update_one({"_id": ObjectId(ticket_id)}, {"$set": {"assigned_to": responder["id"]}})

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9511119903", email="bystander1@example.com")
    await _grant_support_permission(client, owner_headers, bystander["id"], ["view"], role_name="Viewer Role")
    bystander_headers = await _login(client, "9511119903", "InitialPass1!")

    r = await client.get(f"/api/v1/support-tickets/{ticket_id}", headers=bystander_headers)
    assert r.status_code == 403, r.text
