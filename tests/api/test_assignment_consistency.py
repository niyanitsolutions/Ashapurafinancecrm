"""Regression tests for the Application <-> Loan/Insurance Case assignment-consistency
fix, per-application status visibility, Customer registration Source (Lead vs Direct),
and multi-product application independence.

Root cause this locks in: `Application.assigned_to` and `ApplicationWorkflow.assigned_to`
used to be two entirely independent fields — a Case only ever inherited the Application's
assignment once, at creation. `CustomerService.assign_application` and
`LoanCaseService`/`InsuranceCaseService.assign_case` now propagate to each other, so
Loan Management and Customer Applications can never again show a different assignee for
the same underlying case.
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.leads.models import Lead
from app.features.system_settings.models import DocumentType, InsuranceProduct, LeadSource, LoanProduct
from app.features.workflow_engine.constants import CaseType, InsuranceAuditEvent, InsuranceStatus, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition


async def _seed_workflow_definitions(mock_db):
    loan_definition = WorkflowDefinition(
        case_type=CaseType.LOAN, status=LoanStatus.NEW_CUSTOMER, label="New Customer", sequence=1,
        allowed_next_statuses=[LoanStatus.DOCUMENTS_PENDING], audit_event=LoanAuditEvent.CASE_CREATED,
    )
    await mock_db["workflow_definitions"].insert_one(loan_definition.model_dump(by_alias=True, exclude={"id"}))
    insurance_definition = WorkflowDefinition(
        case_type=CaseType.INSURANCE, status=InsuranceStatus.APPLICATION_SUBMITTED, label="Application Submitted", sequence=1,
        allowed_next_statuses=[InsuranceStatus.DOCUMENTS_PENDING], audit_event=InsuranceAuditEvent.CASE_CREATED,
    )
    await mock_db["workflow_definitions"].insert_one(insurance_definition.model_dump(by_alias=True, exclude={"id"}))


async def _seed_product_and_form(mock_db, *, category="loan", product_name="Business Loan"):
    if category == "loan":
        product = LoanProduct(name=product_name)
        collection = "loan_products"
    else:
        product = InsuranceProduct(name=product_name)
        collection = "insurance_products"
    product_id = (await mock_db[collection].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    doc = DocumentType(name=f"PAN-{product_name}")
    doc_id = (await mock_db["document_types"].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    form_def = ApplicationFormDefinition(
        product_category=category, product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=str(doc_id))],
        status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return {"product_category": category, "product_id": str(product_id), "document_type_id": str(doc_id)}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _grant_case_permission(client, owner_headers, employee_id, *, module, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": "applications", "actions": actions}, headers=owner_headers)
    assert r.status_code == 200, r.text
    permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module} {employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _login(client, mobile, password):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _signup_via_otp(client, mobile: str, dev_otp: str, password: str = "CustomerPass1!") -> dict:
    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": dev_otp, "purpose": "signup"})
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": password})
    assert r.status_code == 200, r.text
    return await _login(client, mobile, password)


async def _submitted_application(client, mock_db, product, *, mobile, full_name="AC Test Customer"):
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": full_name}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 100000}}, headers=customer_headers)

    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf"}, headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers, application_id


# ---------------------------------------------------------------------- Part A: multiple products


async def test_customer_can_apply_for_multiple_independent_products(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    loan_product = await _seed_product_and_form(mock_db, category="loan", product_name="Business Loan")
    insurance_product = await _seed_product_and_form(mock_db, category="insurance", product_name="Health Cover")

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9700000101"})
    customer_headers = await _signup_via_otp(client, "9700000101", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Multi Product Customer"}, headers=customer_headers)

    r = await client.post(
        "/api/v1/applications", json={"product_category": "loan", "product_id": loan_product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    app_a = r.json()["data"]["id"]

    # An existing Draft application for Product A must never block starting Application B
    # for a different product.
    r = await client.post(
        "/api/v1/applications", json={"product_category": "insurance", "product_id": insurance_product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    app_b = r.json()["data"]["id"]
    assert app_b != app_a

    r = await client.get("/api/v1/applications/me", headers=customer_headers)
    assert r.status_code == 200, r.text
    ids = {a["id"] for a in r.json()["data"]}
    assert {app_a, app_b} <= ids


async def test_no_existing_duplicate_same_product_rule_is_preserved(client, mock_db, owner_headers):
    # Confirmed via code inspection: no duplicate/active-application rule exists for the
    # same product today. This test locks in that current, intentional behavior rather
    # than accidentally introducing a new restriction.
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9700000102"})
    customer_headers = await _signup_via_otp(client, "9700000102", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Dup Product Customer"}, headers=customer_headers)

    payload = {"product_category": product["product_category"], "product_id": product["product_id"]}
    r1 = await client.post("/api/v1/applications", json=payload, headers=customer_headers)
    r2 = await client.post("/api/v1/applications", json=payload, headers=customer_headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


# ---------------------------------------------------------------------- Part B: registration source


async def test_lead_origin_customer_shows_lead_source_and_preserves_lead_code(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)

    source = LeadSource(name="Walk-In")
    source_id = str((await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    lead = Lead(
        lead_code="AFS-LEAD-000002", full_name="Shabeel Ahamed", mobile="9206105818", email="shabeel@example.com",
        source_id=source_id, product_category=product["product_category"], product_id=product["product_id"],
    )
    lead_id = str((await mock_db["leads"].insert_one(lead.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    r = await client.post(f"/api/v1/leads/{lead_id}/secure-links", json={}, headers=owner_headers)
    secure_code = r.json()["data"]["secure_code"]

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9206105818"})
    customer_headers = await _signup_via_otp(client, "9206105818", r.json()["data"]["dev_otp"])
    r = await client.post(f"/api/v1/secure-links/{secure_code}/claim", headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/customers/me", json={"full_name": "Shabeel Ahamed"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    customer = r.json()["data"]
    assert customer["registration_source"] == "lead"
    assert customer["lead_code"] == "AFS-LEAD-000002"
    assert customer["lead_source_name"] == "Walk-In"

    # Same view from the staff side.
    r = await client.get("/api/v1/customers", headers=owner_headers)
    assert r.status_code == 200, r.text
    row = next(c for c in r.json()["data"] if c["customer_code"] == customer["customer_code"])
    assert row["registration_source"] == "lead"

    r = await client.get(f"/api/v1/customers/{customer['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    detail = r.json()["data"]
    assert detail["registration_source"] == "lead"
    assert detail["lead_code"] == "AFS-LEAD-000002"
    assert detail["lead_source_name"] == "Walk-In"


async def test_direct_customer_shows_direct_source_with_no_fake_lead(client, mock_db, owner_headers):
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9876543210"})
    customer_headers = await _signup_via_otp(client, "9876543210", r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": "Direct Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    customer = r.json()["data"]
    assert customer["registration_source"] == "direct"
    assert customer["lead_code"] is None
    assert customer["lead_source_name"] is None
    assert customer["converted_from_lead_id"] is None

    r = await client.get(f"/api/v1/customers/{customer['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["registration_source"] == "direct"


# ---------------------------------------------------------------------- Part C: assignment consistency


async def test_reassigning_via_loan_case_propagates_to_application(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Assignment Sync Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9700000103")

    r = await client.get("/api/v1/applications", headers=owner_headers)
    assert next(a for a in r.json()["data"] if a["id"] == application_id)["assigned_to_name"] is None

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case = next(c for c in r.json()["data"] if c["application_id"] == application_id)

    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000104", email="loanofficer@example.com")
    r = await client.post(f"/api/v1/loan-cases/{case['id']}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    # Customer Applications must now show the SAME assignee — the exact reported bug.
    r = await client.get(f"/api/v1/applications/{application_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    detail = r.json()["data"]
    assert detail["assigned_to"] == employee["id"]
    assert detail["assigned_to_name"] == "Staff Member"
    assert detail["case_status_label"] == "New Customer"
    assert detail["case_code"] == case["case_code"]

    r = await client.get("/api/v1/applications", headers=owner_headers)
    row = next(a for a in r.json()["data"] if a["id"] == application_id)
    assert row["assigned_to"] == employee["id"]


async def test_reassigning_via_application_propagates_to_loan_case(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Reverse Sync Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9700000105")

    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000106", email="app.assignee@example.com")
    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    assert r.status_code == 200, r.text
    case = next(c for c in r.json()["data"] if c["application_id"] == application_id)
    assert case["assigned_to"] == employee["id"]
    assert case["assigned_to_name"] == "Staff Member"


async def test_two_applications_same_customer_keep_independent_assignments(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    loan_product = await _seed_product_and_form(mock_db, category="loan", product_name="Independent Loan")
    insurance_product = await _seed_product_and_form(mock_db, category="insurance", product_name="Independent Cover")

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9700000107"})
    customer_headers = await _signup_via_otp(client, "9700000107", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Independent Assign Customer"}, headers=customer_headers)

    async def _start_and_submit(product, category):
        r = await client.post("/api/v1/applications", json={"product_category": category, "product_id": product["product_id"]}, headers=customer_headers)
        application_id = r.json()["data"]["id"]
        await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 50000}}, headers=customer_headers)
        upload = await client.post(
            f"/api/v1/applications/{application_id}/documents/upload-url",
            json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf"}, headers=customer_headers,
        )
        s3_key = upload.json()["data"]["s3_key"]
        await client.post(
            f"/api/v1/applications/{application_id}/documents",
            json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
        )
        r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
        assert r.status_code == 200, r.text
        return application_id

    app_a = await _start_and_submit(loan_product, "loan")
    app_b = await _start_and_submit(insurance_product, "insurance")

    employee_a = await _create_employee(client, owner_headers, master_data, mobile="9700000108", email="employee.a@example.com")
    employee_b = await _create_employee(client, owner_headers, master_data, mobile="9700000109", email="employee.b@example.com")

    await client.post(f"/api/v1/applications/{app_a}/assign", json={"employee_id": employee_a["id"]}, headers=owner_headers)
    await client.post(f"/api/v1/applications/{app_b}/assign", json={"employee_id": employee_b["id"]}, headers=owner_headers)

    r = await client.get(f"/api/v1/applications/{app_a}", headers=owner_headers)
    assert r.json()["data"]["assigned_to"] == employee_a["id"]
    r = await client.get(f"/api/v1/applications/{app_b}", headers=owner_headers)
    assert r.json()["data"]["assigned_to"] == employee_b["id"]

    r = await client.get("/api/v1/insurance-cases", headers=owner_headers)
    insurance_case = next(c for c in r.json()["data"] if c["application_id"] == app_b)
    assert insurance_case["assigned_to"] == employee_b["id"]
    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    loan_case = next(c for c in r.json()["data"] if c["application_id"] == app_a)
    assert loan_case["assigned_to"] == employee_a["id"]


async def test_case_reassign_authorization_unchanged(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Auth Check Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9700000110")

    employee = await _create_employee(client, owner_headers, master_data, mobile="9700000111", email="noperm.assign@example.com")
    employee_headers = await _login(client, "9700000111", "InitialPass1!")

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)

    # No "assign" permission yet -> denied.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=employee_headers)
    assert r.status_code == 403, r.text

    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view", "assign"])

    # Self-claim of an unassigned case is allowed.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=employee_headers)
    assert r.status_code == 200, r.text

    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9700000112", email="other.assign@example.com")
    # Reassigning an already-assigned case is Owner-only, even with the "assign" grant.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": other_employee["id"]}, headers=employee_headers)
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": other_employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/applications/{application_id}", headers=owner_headers)
    assert r.json()["data"]["assigned_to"] == other_employee["id"]


# ---------------------------------------------------------------------- Part D: status visibility


async def test_application_response_surfaces_live_case_status(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Status Visibility Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9700000113")

    r = await client.get(f"/api/v1/applications/{application_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    detail = r.json()["data"]
    assert detail["case_status"] == "new_customer"
    assert detail["case_status_label"] == "New Customer"
    assert detail["status"] == "submitted"  # Application status stays independent of Case status


async def test_customer_isolation_unaffected(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    headers_a, application_a = await _submitted_application(client, mock_db, product, mobile="9700000114")
    headers_b, application_b = await _submitted_application(client, mock_db, product, mobile="9700000115")

    r = await client.get(f"/api/v1/applications/{application_b}", headers=headers_a)
    assert r.status_code == 403, r.text
    r = await client.get(f"/api/v1/applications/{application_a}", headers=headers_b)
    assert r.status_code == 403, r.text
