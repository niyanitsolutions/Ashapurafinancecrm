"""Tests for the Loan Management eligibility gate (decision #130): a case must not be
visible/actionable in Loan Management until it has been explicitly moved out of Document
Collection — not merely because a customer account exists, documents were uploaded, or
documents were verified.

Two independent creation paths exist for a Loan Case, and each needs its own coverage:

- **Flow 1 (Lead-originated)**: a Lead moves through My Leads -> Document Collection,
  and only `LeadService.set_stage`'s `loan_management` branch may mark the case moved,
  once its own eligibility checks (submitted + all required documents verified) pass.
- **Flow 2 (lead-less/self-registered)**: a customer registers and applies directly, with
  no Lead/Document Collection pipeline ever involved — there is no "Move to Loan
  Management" action to click, so the case must stay immediately visible, exactly as
  before this fix (this is also what every `_loan_case()`-based fixture in
  `test_case_status_control.py`/`test_loan_bank_offers.py`/`test_assignment_consistency.py`
  relies on, so it must keep working unmodified).
"""

from bson import ObjectId

from app.features.customer.constants import FieldType
from app.features.customer.models import (
    Application,
    ApplicationDocument,
    ApplicationFormDefinition,
    FormFieldDefinition,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import DocumentType, InsuranceProduct, LeadSource, LoanProduct
from app.features.workflow_engine.constants import ON_HOLD_STATUS, CaseType, InsuranceStatus, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition

_LOAN_ROWS = [
    (LoanStatus.NEW_CUSTOMER, "New Customer", 1, [LoanStatus.CREDIT_EVALUATION], LoanAuditEvent.CASE_CREATED),
]
_INSURANCE_ROWS = [
    (InsuranceStatus.APPLICATION_SUBMITTED, "Application Submitted", 1, [InsuranceStatus.DOCUMENTS_PENDING], "insurance_case_created"),
]


async def _seed_workflow_definitions(mock_db):
    for case_type, rows, resumable in ((CaseType.LOAN, _LOAN_ROWS, LoanStatus.RESUMABLE), (CaseType.INSURANCE, _INSURANCE_ROWS, InsuranceStatus.RESUMABLE)):
        for status, label, sequence, allowed_next, audit_event in rows:
            full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status in resumable else allowed_next
            definition = WorkflowDefinition(case_type=case_type, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next, audit_event=audit_event)
            await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))


async def _lead_master_data(mock_db) -> dict:
    source_id = (await mock_db["lead_sources"].insert_one(LeadSource(name="Website").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    loan_id = (await mock_db["loan_products"].insert_one(LoanProduct(name="Personal Loan").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    insurance_id = (await mock_db["insurance_products"].insert_one(InsuranceProduct(name="Health").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"source_id": str(source_id), "loan_product_id": str(loan_id), "insurance_product_id": str(insurance_id)}


async def _create_lead(client, headers, lmd, mobile, assigned_to=None):
    payload = {
        "full_name": "Ravi Kumar", "mobile": mobile, "email": f"{mobile}@example.com", "source_id": lmd["source_id"],
        "product_category": "loan", "product_id": lmd["loan_product_id"], "remarks": "Interested in a personal loan",
    }
    if assigned_to:
        payload["assigned_to"] = assigned_to
    r = await client.post("/api/v1/leads", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _lead_in_document_collection(client, owner_headers, lmd, mobile, employee_id):
    lead = await _create_lead(client, owner_headers, lmd, mobile, assigned_to=employee_id)
    r = await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    return lead


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
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    permission = next((p for p in existing.json()["data"] if p["module"] == module and p["resource"] == "applications"), None)
    if permission is None:
        r = await client.post("/api/v1/permissions", json={"module": module, "resource": "applications", "actions": actions}, headers=owner_headers)
        assert r.status_code == 200, r.text
        permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Visibility Test Role {module} {employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _login(client, mobile, password="InitialPass1!"):
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


async def _seed_document_type(mock_db, name):
    result = await mock_db["document_types"].insert_one(DocumentType(name=name).model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_form_definition(mock_db, product_category, product_id, *, document_type_ids):
    form_def = ApplicationFormDefinition(
        product_category=product_category, product_id=product_id,
        fields=[FormFieldDefinition(key="loan_amount", label="Loan Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=doc_id) for doc_id in document_type_ids],
        status="active",
    )
    result = await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_application(mock_db, *, lead_id, form_definition_id, product_category, product_id, status, customer_id):
    application = Application(
        application_code="AFS-APP-TEST", user_id="000000000000000000000099", lead_id=lead_id, customer_id=customer_id,
        product_category=product_category, product_id=product_id, form_definition_id=form_definition_id, status=status,
    )
    result = await mock_db["applications"].insert_one(application.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_document(mock_db, *, application_id, document_type_id, verification_status):
    document = ApplicationDocument(application_id=application_id, document_type_id=document_type_id, verification_status=verification_status, is_current=True)
    await mock_db["application_documents"].insert_one(document.model_dump(by_alias=True, exclude={"id"}))


async def _lead_originated_verified_application(client, mock_db, owner_headers, lmd, employee_id, *, mobile, customer_id):
    lead = await _lead_in_document_collection(client, owner_headers, lmd, mobile, employee_id)
    pan_id = await _seed_document_type(mock_db, f"PAN-{mobile}")
    form_def_id = await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[pan_id])
    application_id = await _seed_application(
        mock_db, lead_id=lead["id"], form_definition_id=form_def_id, product_category="loan",
        product_id=lmd["loan_product_id"], status="submitted", customer_id=customer_id,
    )
    await _seed_document(mock_db, application_id=application_id, document_type_id=pan_id, verification_status="verified")
    return lead, application_id


async def test_loan_case_hidden_until_moved_to_loan_management(client, mock_db, owner_headers, master_data):
    """Core fix (decision #130): a Lead-originated, fully-submitted, fully-verified
    application must NOT appear in Loan Management's list, counts, or search until the
    Lead is explicitly moved — not because a customer account exists, not because
    documents were uploaded, and not even because documents were already verified."""
    await _seed_workflow_definitions(mock_db)
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9788881001", email="vis1@example.com")
    lead, application_id = await _lead_originated_verified_application(
        client, mock_db, owner_headers, lmd, employee["id"], mobile="9611170001", customer_id="000000000000000000000101",
    )

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert application_id not in {c["application_id"] for c in r.json()["data"]}

    r = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert sum(r.json()["data"].values()) == 0

    move = await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "loan_management"}, headers=owner_headers)
    assert move.status_code == 200, move.text

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    assert application_id in {c["application_id"] for c in r.json()["data"]}

    r = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert sum(r.json()["data"].values()) == 1


async def test_loan_case_direct_get_hidden_before_move_except_for_owner(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9788881002", email="vis2@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view", "edit"])
    employee_headers = await _login(client, "9788881002")
    _lead, application_id = await _lead_originated_verified_application(
        client, mock_db, owner_headers, lmd, employee["id"], mobile="9611170002", customer_id="000000000000000000000102",
    )
    # Triggers `_sync_new_cases()` so the (still-gated) case actually exists to fetch by id.
    await client.get("/api/v1/loan-cases", headers=owner_headers)
    case = await mock_db["application_workflows"].find_one({"application_id": application_id})
    case_id = str(case["_id"])

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.status_code == 404, r.text


async def test_customer_portal_list_and_detail_stay_consistent_before_move(client, mock_db, owner_headers, master_data):
    """Regression guard: `list_own_cases` ("mine") and `get_own_case` (detail) must apply
    the identical eligibility gate — otherwise a customer with portal access to a
    Lead-originated application could see the case in their own list, then get a 404 the
    moment they click into it, before staff completes the move."""
    await _seed_workflow_definitions(mock_db)
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9788881006", email="vis6@example.com")

    mobile = "9611170006"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": "Portal Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    customer_id = r.json()["data"]["id"]
    user_doc = await mock_db["users"].find_one({"mobile": mobile})
    user_id = str(user_doc["_id"])

    lead, application_id = await _lead_originated_verified_application(
        client, mock_db, owner_headers, lmd, employee["id"], mobile="9611170007", customer_id=customer_id,
    )
    # Re-point the seeded application's user_id at this real, logged-in customer.
    await mock_db["applications"].update_one({"_id": ObjectId(application_id)}, {"$set": {"user_id": user_id}})

    r = await client.get("/api/v1/loan-cases/mine", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert application_id not in {c["application_id"] for c in r.json()["data"]}

    await client.get("/api/v1/loan-cases", headers=owner_headers)  # trigger lazy sync
    case = await mock_db["application_workflows"].find_one({"application_id": application_id})
    r = await client.get(f"/api/v1/loan-cases/mine/{case['_id']}", headers=customer_headers)
    assert r.status_code == 404, r.text

    move = await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "loan_management"}, headers=owner_headers)
    assert move.status_code == 200, move.text

    r = await client.get("/api/v1/loan-cases/mine", headers=customer_headers)
    assert application_id in {c["application_id"] for c in r.json()["data"]}
    r = await client.get(f"/api/v1/loan-cases/mine/{case['_id']}", headers=customer_headers)
    assert r.status_code == 200, r.text


async def test_lead_less_loan_application_case_visible_immediately(client, mock_db, owner_headers):
    """Flow 2 (no Lead/Document Collection pipeline ever exists) — the eligibility gate
    doesn't apply; the case must stay visible immediately, exactly as before this fix."""
    await _seed_workflow_definitions(mock_db)
    product = LoanProduct(name="Self-Serve Loan")
    product_id = str((await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    doc_type_id = await _seed_document_type(mock_db, "Self-Serve PAN")
    await _seed_form_definition(mock_db, "loan", product_id, document_type_ids=[doc_type_id])

    mobile = "9611170003"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": "Self Serve Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": product_id}, headers=customer_headers)
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 50000}}, headers=customer_headers)
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": doc_type_id, "file_name": "doc.pdf"}, headers=customer_headers,
    )
    assert upload.status_code == 200, upload.text
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents", json={"document_type_id": doc_type_id, "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    submit = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert submit.status_code == 200, submit.text

    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert application_id in {c["application_id"] for c in r.json()["data"]}

    case = await mock_db["application_workflows"].find_one({"application_id": application_id})
    assert case["moved_to_loan_management_at"] is not None


async def test_insurance_case_visibility_unaffected_by_loan_gate(client, mock_db, owner_headers, master_data):
    """Insurance is completely out of scope for decision #130 — an insurance case must
    remain visible immediately regardless of any Lead-stage state."""
    await _seed_workflow_definitions(mock_db)
    lmd = await _lead_master_data(mock_db)
    employee = await _create_employee(client, owner_headers, master_data, mobile="9788881004", email="vis4@example.com")
    lead = await _create_lead(client, owner_headers, lmd, "9611170004", assigned_to=employee["id"])
    # stage stays "assigned" — never even reaches document_collection — yet the
    # insurance case (created independently of any Lead-stage concept) must still show.
    doc_type_id = await _seed_document_type(mock_db, "Health Declaration")
    form_def_id = await _seed_form_definition(mock_db, "insurance", lmd["insurance_product_id"], document_type_ids=[doc_type_id])
    application_id = await _seed_application(
        mock_db, lead_id=lead["id"], form_definition_id=form_def_id, product_category="insurance",
        product_id=lmd["insurance_product_id"], status="submitted", customer_id="000000000000000000000105",
    )
    await _seed_document(mock_db, application_id=application_id, document_type_id=doc_type_id, verification_status="verified")

    r = await client.get("/api/v1/insurance-cases", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert application_id in {c["application_id"] for c in r.json()["data"]}
