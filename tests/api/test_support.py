"""Customer Portal redesign — minimal Support Ticket module: create (with an optional S3
attachment, reusing the same presigned-upload pattern as ApplicationDocument), list-own
history, customer-only access, and that it keeps firing the existing Module 6B Task/
Notification side-effect (`raise_support_request`) unchanged alongside the new persisted
record.
"""

from test_customer import _signup_via_otp


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
