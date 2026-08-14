"""End-to-end tests for Module 6B (Customer Onboarding & Application Flow): both entry
flows (secure link from an existing Lead, and direct portal registration), reusing
Auth's existing OTP/password/login endpoints unmodified throughout, the dynamic form
engine's required-field/required-document validation at submit time, Lead-to-Customer
conversion (Flow 1 only), and Owner/Employee staff visibility (assignment-scoped for
Employees, unrestricted for Owner).
"""

from datetime import UTC, datetime

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.leads.models import Lead
from app.features.system_settings.models import DocumentType, InsuranceProduct, LoanProduct
from app.features.workflow_engine.constants import CaseType, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition


async def _seed_workflow_definitions(mock_db):
    # A submitted Application lazily creates its Loan/Insurance Case (Module 6C), which
    # needs at least a starting WorkflowDefinition row to exist — seeded for real via
    # scripts/seed.py in production, but this test file exercises submission without ever
    # inserting one itself. Only the one row this file's own tests actually reach
    # (loan:new_customer) is needed; see tests/api/test_workflow.py's own
    # `_seed_workflow_definitions` for the full loan+insurance definition set if a future
    # test here needs to progress a case further than its initial status.
    definition = WorkflowDefinition(
        case_type=CaseType.LOAN, status=LoanStatus.NEW_CUSTOMER, label="New Customer", sequence=1,
        allowed_next_statuses=[LoanStatus.DOCUMENTS_PENDING], audit_event=LoanAuditEvent.CASE_CREATED,
    )
    await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))


async def _seed_product_and_form(mock_db, *, category="loan", product_name="Personal Loan"):
    if category == "loan":
        product = LoanProduct(name=product_name)
        collection = "loan_products"
    else:
        product = InsuranceProduct(name=product_name)
        collection = "insurance_products"
    product_id = (await mock_db[collection].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    pan = DocumentType(name="PAN")
    pan_id = (await mock_db["document_types"].insert_one(pan.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    form_def = ApplicationFormDefinition(
        product_category=category,
        product_id=str(product_id),
        fields=[FormFieldDefinition(key="loan_amount", label="Loan Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=str(pan_id))],
        status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return {"product_category": category, "product_id": str(product_id), "document_type_id": str(pan_id)}


async def _create_lead_doc(mock_db, product, *, mobile="9711111111", full_name="Priya Sharma"):
    lead = Lead(
        lead_code="AFS-LEAD-000001", full_name=full_name, mobile=mobile, email="priya@example.com",
        source_id="000000000000000000000000", product_category=product["product_category"], product_id=product["product_id"],
    )
    lead_id = (await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return str(lead_id)


async def _create_employee(client, owner_headers, master_data, mobile="9511111111", email="staff@example.com"):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _grant_customer_permission(client, owner_headers, employee_id, actions, role_name="Customer Access"):
    # Employee Permission Matrix redesign — GET /customers, /applications (list),
    # document verify/reject now require an explicit `customer:customers` grant (see
    # CustomerViewDep/CustomerEditDep in customer/router.py), additive in front of the
    # existing assigned-application-derived scoping this file's other tests exercise.
    r = await client.post(
        "/api/v1/permissions", json={"module": "customer", "resource": "customers", "actions": ["view", "create", "edit"]},
        headers=owner_headers,
    )
    if r.status_code == 200:
        permission_id = r.json()["data"]["id"]
    else:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        permission_id = next(p["id"] for p in existing.json()["data"] if p["module"] == "customer" and p["resource"] == "customers")

    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"grants": [{"permission_id": permission_id, "granted_actions": actions}]},
        headers=owner_headers,
    )
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _signup_via_otp(client, mobile: str, dev_otp: str, password: str = "CustomerPass1!") -> dict:
    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": dev_otp, "purpose": "signup"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_new_user"] is True
    ticket = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": password})
    assert r.status_code == 200, r.text
    return await _login(client, mobile, password)


# ---------------------------------------------------------------------- Flow 2: direct portal registration


async def test_direct_registration_full_flow(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    mobile = "9722222222"

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    assert dev_otp

    customer_headers = await _signup_via_otp(client, mobile, dev_otp)

    r = await client.post("/api/v1/customers/me", json={"full_name": "Test Customer", "email": "tc@example.com"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    customer = r.json()["data"]
    assert customer["customer_code"].startswith("AFS-CUS-")
    assert customer["converted_from_lead_id"] is None

    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application = r.json()["data"]
    assert application["status"] == "draft"
    assert application["customer_id"] is not None
    application_id = application["id"]

    r = await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 422, r.text  # missing required document

    r = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]
    r = await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "submitted"

    r = await client.get("/api/v1/applications/me", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1


async def test_cannot_register_twice_with_same_mobile(client, mock_db, owner_headers):
    mobile = "9733333333"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    dev_otp = r.json()["data"]["dev_otp"]
    await _signup_via_otp(client, mobile, dev_otp)

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 409, r.text


async def test_direct_registration_is_not_attributed_to_a_seeded_owner(client, mock_db, owner_headers):
    # Decision 053: a direct portal registration must not be linked to any Owner or
    # Employee. Auth's frozen send_otp requires a technical `inviter` to satisfy its
    # signature, but that inviter's id must never persist as attribution on the result.
    mobile = "9700000001"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text

    pending_user = await mock_db["users"].find_one({"mobile": mobile})
    assert pending_user is not None
    assert pending_user["created_by"] is None


# ---------------------------------------------------------------------- Flow 1: secure link from an existing Lead


async def test_secure_link_flow_converts_lead_to_customer(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product)

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    link = r.json()["data"]
    assert link["secure_code"]
    assert link["link_url"].endswith(f"/apply/{link['secure_code']}")
    secure_code = link["secure_code"]

    r = await client.get(f"/api/v1/secure-links/{secure_code}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "valid"
    assert r.json()["data"]["full_name"] == "Priya Sharma"
    assert r.json()["data"]["has_active_account"] is False
    assert "lead_id" not in r.json()["data"]

    # Unified onboarding (decision #047's supersession note): signup for a secure-link
    # customer goes through the same generic, mobile-only registration-start endpoint
    # Flow 2 (direct portal) uses — there is no secure-link-scoped signup step. Linkage
    # to this specific Lead/link only happens later, at the `/claim` call below.
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9711111111"})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]

    customer_headers = await _signup_via_otp(client, "9711111111", dev_otp)

    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    assert r.status_code == 200, r.text
    application = r.json()["data"]
    application_id = application["id"]
    assert application["customer_id"] is None
    assert application["lead_id"] == lead_id

    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 300000}}, headers=customer_headers)
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"}, headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 422, r.text  # no customer_id yet — profile required

    r = await client.post(
        f"/api/v1/applications/{application_id}/submit",
        json={"profile": {"full_name": "Priya Sharma", "email": "priya@example.com"}}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["customer_id"] is not None

    customer_doc = await mock_db["customers"].find_one({"converted_from_lead_id": lead_id})
    assert customer_doc is not None
    assert customer_doc["full_name"] == "Priya Sharma"


async def test_complete_profile_converts_pending_secure_link_application_immediately(client, mock_db, owner_headers):
    """Unified onboarding — completing the one shared profile step right after claiming
    a secure link converts the Lead to a Customer and links the application immediately,
    instead of waiting for submission (see docs/decisions/DECISIONS.md #047's
    supersession note)."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9711111112", full_name="Ananya Rao")

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    secure_code = r.json()["data"]["secure_code"]

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9711111112"})
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, "9711111112", dev_otp)

    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    assert r.status_code == 200, r.text
    application = r.json()["data"]
    application_id = application["id"]
    assert application["customer_id"] is None

    r = await client.post(
        "/api/v1/customers/me", json={"full_name": "Ananya Rao", "email": "ananya@example.com"}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    customer = r.json()["data"]
    assert customer["converted_from_lead_id"] == lead_id

    r = await client.get(f"/api/v1/applications/{application_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["customer_id"] == customer["id"]

    # Submission no longer needs a `profile` payload — the customer already exists.
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 250000}}, headers=customer_headers)
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"}, headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text


async def test_complete_profile_without_pending_application_behaves_as_flow_2(client, mock_db, owner_headers):
    """A direct-portal (Flow 2) customer with no pending secure-link application gets
    `converted_from_lead_id=None`, exactly as before this change."""
    mobile = "9722222223"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, mobile, dev_otp)

    r = await client.post("/api/v1/customers/me", json={"full_name": "Flow Two Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["converted_from_lead_id"] is None


async def test_cannot_generate_secure_link_for_already_converted_lead(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9744444444")
    now = datetime.now(UTC)
    await mock_db["customers"].insert_one(
        {
            "customer_code": "AFS-CUS-000099", "user_id": "000000000000000000000000", "full_name": "Already Converted",
            "mobile": "9744444444", "converted_from_lead_id": lead_id, "status": "active", "is_deleted": False,
            "created_at": now, "updated_at": now, "version": 1,
        }
    )

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    assert r.status_code == 409, r.text


async def test_generating_a_second_secure_link_revokes_the_first(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9744444445")

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    first_code = r.json()["data"]["secure_code"]

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    second = r.json()["data"]
    assert second["secure_code"] != first_code

    r = await client.get(f"/api/v1/secure-links/{first_code}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "disabled"

    r = await client.get(f"/api/v1/secure-links/{second['secure_code']}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "valid"

    r = await client.get(f"/api/v1/leads/{lead_id}/secure-link", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["secure_code"] == second["secure_code"]
    assert r.json()["data"]["created_by_name"] == "Owner"


async def test_disabled_secure_link_blocks_customer_access(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9744444446")

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    link_id = r.json()["data"]["id"]
    secure_code = r.json()["data"]["secure_code"]

    r = await client.post(f"/api/v1/secure-links/{link_id}/disable", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "revoked"

    r = await client.get(f"/api/v1/secure-links/{secure_code}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "disabled"

    # The real enforcement point for a disabled link is `/claim` (see
    # CustomerService._resolve_valid_link -> ForbiddenError), not signup itself — signup
    # is the generic, link-independent registration-start endpoint (see the comment on
    # test_secure_link_flow_converts_lead_to_customer above).
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9744444446"})
    dev_otp = r.json()["data"]["dev_otp"]
    customer_headers = await _signup_via_otp(client, "9744444446", dev_otp)

    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    assert r.status_code == 403, r.text


async def test_expired_secure_link_reports_expired_status(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)
    lead_id = await _create_lead_doc(mock_db, product, mobile="9744444447")

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={"expiry_minutes": 1}, headers=owner_headers)
    secure_code = r.json()["data"]["secure_code"]

    from datetime import timedelta

    await mock_db["secure_links"].update_one(
        {"secure_code": secure_code}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(minutes=1)}}
    )

    r = await client.get(f"/api/v1/secure-links/{secure_code}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "expired"


async def test_unknown_secure_code_reports_not_found_status(client):
    r = await client.get("/api/v1/secure-links/DOESNOTEXIST")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["link_status"] == "not_found"


# ---------------------------------------------------------------------- Owner/Employee staff views


async def test_owner_lists_and_assigns_application_employee_scoped_to_assignment(client, mock_db, owner_headers, master_data):
    product = await _seed_product_and_form(mock_db)
    mobile = "9755555555"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Assign Target"}, headers=customer_headers)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]

    r = await client.get("/api/v1/applications", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(a["id"] == application_id for a in r.json()["data"])

    employee = await _create_employee(client, owner_headers, master_data, mobile="9566666666", email="assignee@example.com")
    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9577777777", email="other@example.com")

    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to"] == employee["id"]

    assignee_headers = await _login(client, "9566666666", "InitialPass1!")
    r = await client.get(f"/api/v1/applications/{application_id}", headers=assignee_headers)
    assert r.status_code == 200, r.text

    other_headers = await _login(client, "9577777777", "InitialPass1!")
    r = await client.get(f"/api/v1/applications/{application_id}", headers=other_headers)
    assert r.status_code == 403, r.text

    # GET /applications (list) now also requires the customer:customers:view grant —
    # without it, an Employee is blocked before the existing assignment-scoping even runs.
    r = await client.get("/api/v1/applications", headers=other_headers)
    assert r.status_code == 403, r.text

    await _grant_customer_permission(client, owner_headers, other_employee["id"], ["view"])
    r = await client.get("/api/v1/applications", headers=other_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []

    # Assign is Owner-only
    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": other_employee["id"]}, headers=assignee_headers)
    assert r.status_code == 403, r.text


async def test_unassigned_applications_queue_is_owner_only(client, mock_db, owner_headers, master_data):
    # Decision 053: direct-registration applications land in an "Unassigned Applications"
    # queue for the Owner to review and assign — `unassigned_only` is force-disabled for
    # Employees since work assigned to nobody isn't theirs to see.
    product = await _seed_product_and_form(mock_db)
    mobile = "9700000002"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Unassigned Target"}, headers=customer_headers)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]

    r = await client.get("/api/v1/applications?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(a["id"] == application_id for a in r.json()["data"])

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9500000003", email="bystander@example.com")
    bystander_headers = await _login(client, "9500000003", "InitialPass1!")
    await _grant_customer_permission(client, owner_headers, bystander["id"], ["view"], role_name="Bystander Access")
    r = await client.get("/api/v1/applications?unassigned_only=true", headers=bystander_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []  # unassigned_only is ignored for Employees, not proxied through

    employee = await _create_employee(client, owner_headers, master_data, mobile="9500000002", email="unassigned-assignee@example.com")
    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/applications?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert all(a["id"] != application_id for a in r.json()["data"])


# ---------------------------------------------------------------------- customer:customers permission gate


async def test_list_customers_requires_customer_view_permission(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9500000010", email="noperm.customer@example.com")
    headers = await _login(client, "9500000010", "InitialPass1!")

    r = await client.get("/api/v1/customers", headers=headers)
    assert r.status_code == 403, r.text

    await _grant_customer_permission(client, owner_headers, employee["id"], ["view"])
    r = await client.get("/api/v1/customers", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []  # granted, but no assigned customers yet — record scope unchanged


async def test_document_verify_reject_require_customer_edit_permission(client, mock_db, owner_headers, master_data):
    employee = await _create_employee(client, owner_headers, master_data, mobile="9500000011", email="noedit.customer@example.com")
    headers = await _login(client, "9500000011", "InitialPass1!")
    dummy_id = "000000000000000000000000"

    # The permission dependency runs before route logic, so a missing grant 403s even
    # against a nonexistent application/document — no real document needs to exist for
    # this to prove the gate is active.
    r = await client.patch(f"/api/v1/applications/{dummy_id}/documents/{dummy_id}/verify", headers=headers)
    assert r.status_code == 403, r.text
    r = await client.patch(f"/api/v1/applications/{dummy_id}/documents/{dummy_id}/reject", json={"reason": "blurry"}, headers=headers)
    assert r.status_code == 403, r.text

    await _grant_customer_permission(client, owner_headers, employee["id"], ["view", "edit"])
    r = await client.patch(f"/api/v1/applications/{dummy_id}/documents/{dummy_id}/verify", headers=headers)
    assert r.status_code == 404, r.text  # past the permission gate now, fails on "not found" instead


async def test_owner_customer_access_unaffected_by_new_permission_gate(client, mock_db, owner_headers):
    # Owner holds zero explicit grants anywhere — PermissionEngine's unconditional Owner
    # bypass means the new customer:customers gate never blocks them.
    r = await client.get("/api/v1/customers", headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/applications", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_customer_cannot_view_another_customers_application(client, mock_db, owner_headers):
    product = await _seed_product_and_form(mock_db)

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9788888888"})
    headers_a = await _signup_via_otp(client, "9788888888", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Customer A"}, headers=headers_a)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=headers_a
    )
    application_id = r.json()["data"]["id"]

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9799999999"})
    headers_b = await _signup_via_otp(client, "9799999999", r.json()["data"]["dev_otp"])

    r = await client.get(f"/api/v1/applications/{application_id}", headers=headers_b)
    assert r.status_code == 403, r.text
