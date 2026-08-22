"""Production stabilization pass — "Message your RM": a new, additive two-way
Customer<->Staff conversation module (no prior module built one to reuse — Module 9C's
Communication Engine is one-way outbound only). Covers: lazy get-or-create conversation,
RM resolution reuse (the same fix from the portal dashboard's own RM display), staff
list/reply, and the IDOR boundary (an employee not assigned to the customer cannot see
or reply to their conversation).
"""

from bson import ObjectId

from test_customer import _create_employee, _seed_product_and_form, _signup_via_otp


async def _register_customer(client, mock_db, *, mobile: str) -> dict:
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, mobile, dev_otp)
    r = await client.post("/api/v1/customers/me", json={"full_name": "Kiran Rao", "email": "kiran@example.com"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _grant_messaging_permission(client, owner_headers, employee_id, actions, role_name="Messaging Role"):
    r = await client.post(
        "/api/v1/permissions", json={"module": "messaging", "resource": "conversations", "actions": ["view", "create"]}, headers=owner_headers
    )
    if r.status_code == 200:
        permission_id = r.json()["data"]["id"]
    else:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission_id = next(p["id"] for p in existing.json()["data"] if p["module"] == "messaging" and p["resource"] == "conversations")
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission_id, "granted_actions": actions}]}, headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def test_customer_conversation_is_lazily_created_and_empty_initially(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9644440001")
    r = await client.get("/api/v1/conversations/me", headers=customer_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["messages"] == []
    assert data["employee_id"] is None


async def test_end_to_end_customer_sends_staff_replies_customer_sees_reply(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9511119910", email="rm-messaging@example.com")
    customer_headers = await _register_customer(client, mock_db, mobile="9644440002")

    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)

    r = await client.post("/api/v1/conversations/me/messages", json={"body": "Hi, need help with my application"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["employee_id"] == employee["id"]
    assert len(data["messages"]) == 1
    assert data["messages"][0]["sender_role"] == "customer"

    await _grant_messaging_permission(client, owner_headers, employee["id"], ["view", "create"])
    staff_headers = await _login(client, "9511119910", "InitialPass1!")

    r = await client.get("/api/v1/conversations", headers=staff_headers)
    assert r.status_code == 200, r.text
    conversations = r.json()["data"]
    assert len(conversations) == 1
    conversation_id = conversations[0]["id"]

    r = await client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"body": "Sure, what's the issue?"}, headers=staff_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["messages"][-1]["sender_role"] == "staff"
    assert r.json()["data"]["messages"][-1]["sender_name"] == "Staff Member"

    r = await client.get("/api/v1/conversations/me", headers=customer_headers)
    messages = r.json()["data"]["messages"]
    assert len(messages) == 2
    assert messages[-1]["body"] == "Sure, what's the issue?"
    assert messages[-1]["sender_role"] == "staff"


async def test_unassigned_customer_message_is_visible_to_owner(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9644440003")
    r = await client.post("/api/v1/conversations/me/messages", json={"body": "Anyone there?"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["employee_id"] is None

    r = await client.get("/api/v1/conversations", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1


async def test_employee_not_assigned_cannot_see_or_reply_to_conversation(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    rm = await _create_employee(client, owner_headers, master_data, mobile="9511119911", email="assignedrm1@example.com")
    other = await _create_employee(client, owner_headers, master_data, mobile="9511119912", email="unrelated1@example.com")
    await _grant_messaging_permission(client, owner_headers, other["id"], ["view", "create"], role_name="Other Role")
    other_headers = await _login(client, "9511119912", "InitialPass1!")

    customer_headers = await _register_customer(client, mock_db, mobile="9644440004")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": rm["id"]}, headers=owner_headers)
    await client.post("/api/v1/conversations/me/messages", json={"body": "Hello"}, headers=customer_headers)

    conversations = await mock_db["conversations"].find({}).to_list(length=10)
    conversation_id = str(conversations[0]["_id"])

    r = await client.get(f"/api/v1/conversations/{conversation_id}", headers=other_headers)
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"body": "Butting in"}, headers=other_headers)
    assert r.status_code == 403, r.text

    # And is absent from that employee's own list.
    r = await client.get("/api/v1/conversations", headers=other_headers)
    assert r.status_code == 200, r.text
    assert conversation_id not in [c["id"] for c in r.json()["data"]]


async def test_conversations_require_permission(client, mock_db, owner_headers, employee_headers):
    r = await client.get("/api/v1/conversations", headers=employee_headers)
    assert r.status_code == 403, r.text


async def test_empty_message_body_rejected(client, mock_db, owner_headers):
    customer_headers = await _register_customer(client, mock_db, mobile="9644440005")
    r = await client.post("/api/v1/conversations/me/messages", json={"body": "   "}, headers=customer_headers)
    assert r.status_code == 422, r.text
