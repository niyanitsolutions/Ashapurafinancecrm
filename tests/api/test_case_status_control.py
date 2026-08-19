"""Tests for the generic Case Status control (Loan/Insurance Case detail pages) —
`PATCH /loan-cases/{id}/status` and `PATCH /insurance-cases/{id}/status`. These reuse the
existing Workflow Engine (`WorkflowEngine.transition`/`assert_transition_allowed`) and the
existing `request_documents`/`verify_documents` service methods rather than a second
status-writing path — see `LoanCaseService.update_status`'s own docstring for exactly
which transitions this control can execute directly vs. reject in favor of the existing
dedicated action (Credit Evaluation, Disbursement, Hold, ...).
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import (
    ApplicationFormDefinition,
    FormFieldDefinition,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import DocumentType, InsuranceProduct, LoanProduct
from app.features.workflow_engine.constants import (
    ON_HOLD_STATUS,
    CaseType,
    InsuranceStatus,
    LoanAuditEvent,
    LoanStatus,
)
from app.features.workflow_engine.models import WorkflowDefinition

# Mirrors test_workflow.py's own `_LOAN_ROWS`/`_INSURANCE_ROWS` seed shape — kept as a
# separate, local copy (same convention every other test module in this suite already
# follows) rather than a cross-module import.
_LOAN_ROWS = [
    (LoanStatus.NEW_CUSTOMER, "New Customer", 1, [LoanStatus.DOCUMENTS_PENDING], LoanAuditEvent.CASE_CREATED),
    (LoanStatus.DOCUMENTS_PENDING, "Documents Pending", 2, [LoanStatus.CREDIT_EVALUATION], LoanAuditEvent.DOCUMENTS_REQUESTED),
    (LoanStatus.CREDIT_EVALUATION, "Credit Evaluation", 3, [LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED], LoanAuditEvent.DOCUMENTS_VERIFIED),
    (LoanStatus.OFFER_ACCEPTANCE, "Offer Acceptance", 4, [LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.REJECTED], LoanAuditEvent.CREDIT_EVALUATED),
    (LoanStatus.ADDITIONAL_DOCUMENTS, "Upload Additional Documents", 5, [LoanStatus.ESIGN_NACH_KYC], LoanAuditEvent.OFFER_ACCEPTED),
    (LoanStatus.ESIGN_NACH_KYC, "eSign / NACH / KYC", 6, [LoanStatus.FINAL_EVALUATION], LoanAuditEvent.ADDITIONAL_DOCS_VERIFIED),
    (LoanStatus.FINAL_EVALUATION, "Final Evaluation", 7, [LoanStatus.SEND_FOR_DISBURSEMENT, LoanStatus.REJECTED], LoanAuditEvent.ESIGN_NACH_KYC_COMPLETED),
    (LoanStatus.SEND_FOR_DISBURSEMENT, "Send For Disbursement", 8, [LoanStatus.DISBURSED], LoanAuditEvent.FINAL_EVALUATED),
    (LoanStatus.DISBURSED, "Disbursed", 9, [], LoanAuditEvent.DISBURSED),
    (LoanStatus.REJECTED, "Application Rejected", 10, [], LoanAuditEvent.REJECTED),
]
_INSURANCE_ROWS = [
    (InsuranceStatus.APPLICATION_SUBMITTED, "Application Submitted", 1, [InsuranceStatus.DOCUMENTS_PENDING], "insurance_case_created"),
    (InsuranceStatus.DOCUMENTS_PENDING, "Documents Pending", 2, [InsuranceStatus.UNDERWRITING], "insurance_case_documents_requested"),
    (InsuranceStatus.UNDERWRITING, "Underwriting", 3, [InsuranceStatus.MEDICAL_VERIFICATION, InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED], "insurance_case_documents_verified"),
    (InsuranceStatus.MEDICAL_VERIFICATION, "Medical Verification", 4, [InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED], "insurance_case_medical_verification_required"),
    (InsuranceStatus.ADDITIONAL_DOCUMENTS, "Additional Documents", 5, [InsuranceStatus.PREMIUM_ACCEPTANCE], "insurance_case_additional_documents_required"),
    (InsuranceStatus.PREMIUM_ACCEPTANCE, "Premium Acceptance", 6, [InsuranceStatus.POLICY_GENERATION, InsuranceStatus.REJECTED], "insurance_case_premium_ready"),
    (InsuranceStatus.POLICY_GENERATION, "Policy Generation", 7, [InsuranceStatus.POLICY_ISSUED], "insurance_case_premium_accepted"),
    (InsuranceStatus.POLICY_ISSUED, "Policy Issued", 8, [], "insurance_case_policy_issued"),
    (InsuranceStatus.REJECTED, "Application Rejected", 9, [], "insurance_case_rejected"),
]


async def _seed_workflow_definitions(mock_db):
    for case_type, rows, resumable in ((CaseType.LOAN, _LOAN_ROWS, LoanStatus.RESUMABLE), (CaseType.INSURANCE, _INSURANCE_ROWS, InsuranceStatus.RESUMABLE)):
        for status, label, sequence, allowed_next, audit_event in rows:
            full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status in resumable else allowed_next
            definition = WorkflowDefinition(case_type=case_type, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next, audit_event=audit_event)
            await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))
        on_hold_definition = WorkflowDefinition(
            case_type=case_type, status=ON_HOLD_STATUS, label="On Hold", sequence=len(rows) + 1,
            allowed_next_statuses=list(resumable), audit_event="workflow_case_on_hold",
        )
        await mock_db["workflow_definitions"].insert_one(on_hold_definition.model_dump(by_alias=True, exclude={"id"}))


async def _seed_product_and_form(mock_db, *, category="loan", product_name="Personal Loan"):
    if category == "loan":
        product = LoanProduct(name=product_name)
        collection = "loan_products"
    else:
        product = InsuranceProduct(name=product_name)
        collection = "insurance_products"
    product_id = (await mock_db[collection].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    pan = DocumentType(name=f"PAN-{product_name}")
    pan_id = (await mock_db["document_types"].insert_one(pan.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    form_def = ApplicationFormDefinition(
        product_category=category, product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=str(pan_id))], status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return {"product_category": category, "product_id": str(product_id), "document_type_id": str(pan_id)}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
        "department_id": master_data["department_id"], "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
        "joining_date": "2026-01-15", "employment_type": "full_time",
    }
    r = await client.post("/api/v1/employees", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


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


async def _submitted_application(client, mock_db, product, *, mobile):
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": "Status Control Test Customer"}, headers=customer_headers)
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
    assert upload.status_code == 200, upload.text
    s3_key = upload.json()["data"]["s3_key"]
    confirm = await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    assert confirm.status_code == 200, confirm.text

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers, application_id


async def _grant_case_permission(client, owner_headers, employee_id, *, module, actions):
    # The catalog entry for a (module, "applications") pair is created once per module —
    # a test that grants the same module to two different employees (e.g. the primary
    # assignee via `_loan_case` and a second "bystander" employee) must reuse it, not
    # attempt to create it twice (POST /permissions 409s on a duplicate module+resource).
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    permission = next((p for p in existing.json()["data"] if p["module"] == module and p["resource"] == "applications"), None)
    if permission is None:
        r = await client.post("/api/v1/permissions", json={"module": module, "resource": "applications", "actions": actions}, headers=owner_headers)
        assert r.status_code == 200, r.text
        permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Status Control Role {module} {employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _loan_case(client, mock_db, owner_headers, master_data, *, mobile_suffix):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name=f"Loan {mobile_suffix}")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile=f"96{mobile_suffix}")
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    employee = await _create_employee(client, owner_headers, master_data, mobile=f"97{mobile_suffix}", email=f"loan{mobile_suffix}@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view", "edit", "approve", "assign"])
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    employee_headers = await _login(client, f"97{mobile_suffix}")
    return case_id, employee_headers, customer_headers, application_id


async def _insurance_case(client, mock_db, owner_headers, master_data, *, mobile_suffix):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="insurance", product_name=f"Insurance {mobile_suffix}")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile=f"96{mobile_suffix}")
    r = await client.get("/api/v1/insurance-cases?unassigned_only=true", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    employee = await _create_employee(client, owner_headers, master_data, mobile=f"97{mobile_suffix}", email=f"ins{mobile_suffix}@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], module="insurance_management", actions=["view", "edit", "approve", "assign"])
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    employee_headers = await _login(client, f"97{mobile_suffix}")
    return case_id, employee_headers, customer_headers, application_id


# ---------------------------------------------------------------------- 1/3: valid update persists (Loan/Insurance)


async def test_valid_loan_status_update_persists_and_reflects_in_list(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _customer_headers, _application_id = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000001")

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"

    # Refetch (simulates a browser refresh) — database is the only source of truth.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "documents_pending"

    # List reflects it immediately, and the status filter finds it by the exact value.
    r = await client.get("/api/v1/loan-cases?status=documents_pending", headers=employee_headers)
    assert case_id in [c["id"] for c in r.json()["data"]]
    r = await client.get("/api/v1/loan-cases?status=new_customer", headers=employee_headers)
    assert case_id not in [c["id"] for c in r.json()["data"]]


async def test_valid_insurance_status_update_persists_and_reflects_in_list(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _customer_headers, _application_id = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000002")

    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"

    r = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "documents_pending"

    r = await client.get("/api/v1/insurance-cases?status=documents_pending", headers=employee_headers)
    assert case_id in [c["id"] for c in r.json()["data"]]
    r = await client.get("/api/v1/insurance-cases?status=application_submitted", headers=employee_headers)
    assert case_id not in [c["id"] for c in r.json()["data"]]


# ---------------------------------------------------------------------- 2/4: cross-case-type / invalid status rejected


async def test_loan_status_endpoint_rejects_insurance_only_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000003")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "underwriting"}, headers=employee_headers)
    assert r.status_code == 422, r.text
    # Status must remain untouched.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "new_customer"


async def test_insurance_status_endpoint_rejects_loan_only_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000004")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 422, r.text
    r = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "application_submitted"


async def test_loan_status_endpoint_rejects_nonsense_status_value(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000005")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "not_a_real_status"}, headers=employee_headers)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- 5/6: unauthorized rejected


async def test_unauthorized_employee_cannot_update_loan_status(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000006")
    await _create_employee(client, owner_headers, master_data, mobile="9711100006", email="bystander-loan@example.com")
    bystander_headers = await _login(client, "9711100006")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=bystander_headers)
    assert r.status_code == 403, r.text


async def test_unauthorized_employee_cannot_update_insurance_status(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000007")
    await _create_employee(client, owner_headers, master_data, mobile="9711100007", email="bystander-ins@example.com")
    bystander_headers = await _login(client, "9711100007")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "documents_pending"}, headers=bystander_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- 7: non-existent case -> 404


async def test_status_update_on_nonexistent_loan_case_returns_404(client, owner_headers):
    r = await client.patch("/api/v1/loan-cases/000000000000000000000000/status", json={"status": "documents_pending"}, headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_status_update_on_nonexistent_insurance_case_returns_404(client, owner_headers):
    r = await client.patch("/api/v1/insurance-cases/000000000000000000000000/status", json={"status": "documents_pending"}, headers=owner_headers)
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------- 8/9: history — recorded once, no duplicate on no-op


async def test_same_status_update_is_a_noop_with_no_duplicate_history(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000008")

    r = await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)
    before = len([e for e in r.json()["data"] if e["type"] == "status"])

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "new_customer"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "new_customer"

    r = await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)
    after = len([e for e in r.json()["data"] if e["type"] == "status"])
    assert after == before  # no history entry added for a same-status "change"


async def test_status_history_records_previous_and_new_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000009")

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)
    status_entries = [e for e in r.json()["data"] if e["type"] == "status"]
    entry = next(e for e in status_entries if e["to_status"] == "documents_pending")
    assert entry["from_status"] == "new_customer"
    assert entry["created_by"] is not None
    assert entry["created_at"] is not None


# ---------------------------------------------------------------------- 12: assignment/tenant isolation preserved


async def test_employee_not_assigned_to_case_is_forbidden(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000010")
    other = await _create_employee(client, owner_headers, master_data, mobile="9711100010", email="other-officer@example.com")
    await _grant_case_permission(client, owner_headers, other["id"], module="loan_management", actions=["view", "edit"])
    other_headers = await _login(client, "9711100010")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=other_headers)
    assert r.status_code == 403, r.text  # this case isn't assigned to them


# ---------------------------------------------------------------------- 13/14: Customer Portal reflects the live status


async def test_customer_portal_reflects_updated_loan_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _application_id = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000011")

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.json()["data"]["current_status"] == "new_customer"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"  # must not still show the old status


async def test_customer_portal_reflects_updated_insurance_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _application_id = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000012")

    r = await client.get(f"/api/v1/insurance-cases/mine/{case_id}", headers=customer_headers)
    assert r.json()["data"]["current_status"] == "application_submitted"

    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/insurance-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"


async def test_customer_application_timeline_reflects_updated_loan_status(client, mock_db, owner_headers, master_data):
    """The Customer Portal's actual status display (ApplicationTimelinePage.tsx) reads
    `GET /applications/{id}/timeline`, which marks whichever WorkflowDefinition matches
    the case's live `current_status` as "current" — not a second, independently-tracked
    Application status. This is the concrete customer-facing surface §9 requires."""
    case_id, employee_headers, customer_headers, application_id = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000013")

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    assert r.status_code == 200, r.text
    current_entries = [e for e in r.json()["data"] if e.get("state") == "current"]
    assert any(e["label"] == "Documents Pending" for e in current_entries)


# ---------------------------------------------------------------------- existing business rules preserved through the generic control


async def test_generic_status_update_still_enforces_document_upload_precondition(client, mock_db, owner_headers, master_data):
    """documents_pending -> credit_evaluation is a "simple" transition (dispatches into
    the existing `verify_documents`), but that method's own precondition — every
    requested document must actually be uploaded — must still apply through this
    control, exactly as it does through the dedicated `/documents/verify` endpoint."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000014")

    # `request_documents` only accepts new requests from New Customer/Additional
    # Documents — use the dedicated request endpoint (with a real, never-uploaded
    # document type) to both enter Documents Pending AND leave something outstanding,
    # so the generic control's dispatch to `verify_documents` has something to reject.
    extra_doc = DocumentType(name="Extra Required Doc")
    extra_doc_id = str((await mock_db["document_types"].insert_one(extra_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/request", json={"document_type_ids": [extra_doc_id]}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 422, r.text  # extra_doc was never uploaded — same rule as the dedicated verify endpoint
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "documents_pending"  # unchanged


async def test_generic_status_update_rejects_transition_requiring_dedicated_action(client, mock_db, owner_headers, master_data):
    """credit_evaluation -> offer_acceptance requires a real credit decision (score,
    remarks, approve/reject) the generic {"status": ...} body can't carry — must be
    rejected, not silently executed with no decision recorded."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000015")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/verify", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "offer_acceptance"}, headers=employee_headers)
    assert r.status_code == 409, r.text
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "credit_evaluation"  # unchanged — no decision was recorded


async def test_generic_status_update_rejects_out_of_order_jump(client, mock_db, owner_headers, master_data):
    """Existing transition-graph rules (WorkflowDefinition.allowed_next_statuses) are
    preserved: New Customer cannot jump straight to Disbursed."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000016")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "disbursed"}, headers=employee_headers)
    assert r.status_code == 422, r.text
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "new_customer"


async def test_owner_can_update_loan_status(client, mock_db, owner_headers, master_data):
    """Owner bypasses the permission engine entirely — unaffected by this new endpoint."""
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000017")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"
