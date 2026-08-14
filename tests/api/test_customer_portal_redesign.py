"""Customer Portal redesign — regression coverage for the three additive backend changes:
document verification status (create/verify/reject + assignment-scoping), the Application
list's new `progress_percent`, and Timeline attribution (`actor_name` + the Lead-assignment
entry). Support tickets are covered in `test_support.py`.
"""

from app.utils.helpers import to_object_id
from test_customer import _create_employee, _create_lead_doc, _seed_product_and_form, _signup_via_otp


async def _register_customer(client, mock_db, *, mobile: str) -> dict:
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, mobile, dev_otp)
    r = await client.post("/api/v1/customers/me", json={"full_name": "Vijay Kumar", "email": "vijay@example.com"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers


async def _create_application_with_document(client, mock_db, product, customer_headers):
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"}, headers=customer_headers,
    )
    s3_key = r.json()["data"]["s3_key"]
    r = await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    document_id = r.json()["data"]["id"]
    return application_id, document_id


# ---------------------------------------------------------------------- document verification


async def test_new_document_defaults_to_pending(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222201")
    _application_id, document_id = await _create_application_with_document(client, mock_db, product, customer_headers)

    doc = await mock_db["application_documents"].find_one({"_id": to_object_id(document_id)})
    assert doc["verification_status"] == "pending"


async def test_owner_verifies_document(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222202")
    application_id, document_id = await _create_application_with_document(client, mock_db, product, customer_headers)

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{document_id}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["verification_status"] == "verified"
    assert data["verified_at"] is not None
    assert data["rejection_reason"] is None

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=customer_headers)
    assert r.json()["data"][0]["verification_status"] == "verified"


async def test_owner_rejects_document_with_reason(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222203")
    application_id, document_id = await _create_application_with_document(client, mock_db, product, customer_headers)

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject",
        json={"reason": "Blurry scan, please re-upload"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["verification_status"] == "rejected"
    assert data["rejection_reason"] == "Blurry scan, please re-upload"

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=customer_headers)
    assert r.json()["data"][0]["rejection_reason"] == "Blurry scan, please re-upload"


async def test_unassigned_employee_cannot_verify_document(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222204")
    application_id, document_id = await _create_application_with_document(client, mock_db, product, customer_headers)

    employee = await _create_employee(client, owner_headers, master_data, mobile="9511122204", email="notassigned@example.com")
    r = await client.post("/api/v1/auth/login", json={"mobile": "9511122204", "password": "InitialPass1!"})
    employee_headers = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{document_id}/verify", headers=employee_headers)
    assert r.status_code == 403, r.text
    assert employee["id"]  # sanity: employee exists but simply isn't assigned to this application


async def test_customer_cannot_verify_own_document(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222205")
    application_id, document_id = await _create_application_with_document(client, mock_db, product, customer_headers)

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{document_id}/verify", headers=customer_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- application list progress_percent


async def test_application_list_reports_progress_percent(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    customer_headers = await _register_customer(client, mock_db, mobile="9622222206")
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]

    r = await client.get("/api/v1/applications/me", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"][0]["progress_percent"] == 0

    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    r = await client.get("/api/v1/applications/me", headers=customer_headers)
    assert r.json()["data"][0]["progress_percent"] == 100


# ---------------------------------------------------------------------- timeline attribution


async def test_timeline_includes_lead_assignment_entry(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product)

    employee = await _create_employee(client, owner_headers, master_data, mobile="9511122207", email="rm.timeline@example.com")
    r = await client.post(f"/api/v1/leads/{lead_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    secure_code = r.json()["data"]["secure_code"]
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9711111111"})
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, "9711111111", dev_otp)
    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    application_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    assert r.status_code == 200, r.text
    entries = r.json()["data"]
    assigned_entry = next((e for e in entries if e["label"] == f"Assigned to {employee['display_name']}"), None)
    assert assigned_entry is not None
    assert assigned_entry["state"] == "completed"
    assert assigned_entry["occurred_at"] is not None


async def test_timeline_omits_assignment_entry_when_lead_never_assigned(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9711111199")

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    secure_code = r.json()["data"]["secure_code"]
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9711111199"})
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, "9711111199", dev_otp)
    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    application_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    labels = [e["label"] for e in r.json()["data"]]
    assert not any(label.startswith("Assigned to") for label in labels)
