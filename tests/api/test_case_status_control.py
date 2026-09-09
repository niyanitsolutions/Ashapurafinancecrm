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
    (LoanStatus.NEW_CUSTOMER, "New Customer", 1, [LoanStatus.CREDIT_EVALUATION], LoanAuditEvent.CASE_CREATED),
    (
        LoanStatus.CREDIT_EVALUATION, "Credit Evaluation", 2,
        [LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED, LoanStatus.RE_ELIGIBLE], LoanAuditEvent.CREDIT_EVALUATED,
    ),
    (LoanStatus.OFFER_ACCEPTANCE, "Offer Acceptance", 3, [LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.REJECTED], LoanAuditEvent.BANK_OFFER_SELECTED),
    (LoanStatus.ADDITIONAL_DOCUMENTS, "Additional Documents", 4, [LoanStatus.RV_OV_REF], LoanAuditEvent.OFFER_ACCEPTED),
    (LoanStatus.RV_OV_REF, "RV/OV/Ref", 5, [LoanStatus.ESIGN_NACH_KYC], LoanAuditEvent.ADDITIONAL_DOCS_VERIFIED),
    (LoanStatus.ESIGN_NACH_KYC, "eSign / NACH / KYC", 6, [LoanStatus.FINAL_EVALUATION], LoanAuditEvent.RV_OV_REF_COMPLETED),
    (LoanStatus.FINAL_EVALUATION, "Final Evaluation", 7, [LoanStatus.SEND_FOR_DISBURSEMENT, LoanStatus.REJECTED], LoanAuditEvent.ESIGN_NACH_KYC_COMPLETED),
    (LoanStatus.SEND_FOR_DISBURSEMENT, "Send For Disbursement", 8, [LoanStatus.DISBURSED], LoanAuditEvent.FINAL_EVALUATED),
    (LoanStatus.DISBURSED, "Disbursed", 9, [], LoanAuditEvent.DISBURSED),
    (
        LoanStatus.RE_ELIGIBLE, "Re-Eligible", 10,
        [LoanStatus.NEW_CUSTOMER, LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED], LoanAuditEvent.MARKED_RE_ELIGIBLE,
    ),
    (LoanStatus.REJECTED, "Application Rejected", 11, [LoanStatus.RE_ELIGIBLE], LoanAuditEvent.REJECTED),
]
_INSURANCE_ROWS = [
    (InsuranceStatus.FRESH_LEAD, "Fresh Lead", 1, [InsuranceStatus.POLICY_DOCUMENT, InsuranceStatus.REJECTED], "insurance_case_created"),
    (InsuranceStatus.POLICY_DOCUMENT, "Policy Document", 2, [InsuranceStatus.POLICY_LOGIN, InsuranceStatus.REJECTED], "insurance_case_policy_document_started"),
    (InsuranceStatus.POLICY_LOGIN, "Policy Login", 3, [InsuranceStatus.POLICY_ISSUED, InsuranceStatus.REJECTED], "insurance_case_policy_login_started"),
    (InsuranceStatus.POLICY_ISSUED, "Policy Issued", 4, [], "insurance_case_policy_issued"),
    (InsuranceStatus.RE_ELIGIBLE, "Re-Eligible", 5, [InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT, InsuranceStatus.REJECTED], "insurance_case_marked_re_eligible"),
    (InsuranceStatus.REJECTED, "Application Rejected", 6, [InsuranceStatus.RE_ELIGIBLE], "insurance_case_rejected"),
]
_INSURANCE_ALLOWED_PREVIOUS = {
    InsuranceStatus.POLICY_DOCUMENT: [InsuranceStatus.FRESH_LEAD],
    InsuranceStatus.POLICY_LOGIN: [InsuranceStatus.POLICY_DOCUMENT],
}


async def _seed_workflow_definitions(mock_db):
    for case_type, rows, resumable, allowed_previous in (
        (CaseType.LOAN, _LOAN_ROWS, LoanStatus.RESUMABLE, {}),
        (CaseType.INSURANCE, _INSURANCE_ROWS, InsuranceStatus.RESUMABLE, _INSURANCE_ALLOWED_PREVIOUS),
    ):
        for status, label, sequence, allowed_next, audit_event in rows:
            full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status in resumable else allowed_next
            definition = WorkflowDefinition(
                case_type=case_type, status=status, label=label, sequence=sequence,
                allowed_next_statuses=full_allowed_next, allowed_previous_statuses=allowed_previous.get(status, []),
                audit_event=audit_event,
            )
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
    # Production fix "DC vs LM" — a Lead-less submitted application (this helper's own
    # flow, via `_submitted_application`) now stages in Document Collection like any
    # other application; it must be explicitly moved (all required documents verified
    # first) before it becomes a Loan Case at all, so every downstream case-status test
    # this helper feeds still gets a real, already-in-Loan-Management case to work with.
    await mock_db["application_documents"].update_one(
        {"application_id": application_id, "document_type_id": product["document_type_id"], "is_current": True},
        {"$set": {"verification_status": "verified"}},
    )
    move = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert move.status_code == 200, move.text
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

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    # The remaining plain-control pair `credit_evaluation -> re_eligible` is the one
    # actually under test here (decision #132 made `new_customer -> credit_evaluation` a
    # dedicated action, not a plain-control move).
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"

    # Refetch (simulates a browser refresh) — database is the only source of truth.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "re_eligible"

    # List reflects it immediately, and the status filter finds it by the exact value.
    r = await client.get("/api/v1/loan-cases?status=re_eligible", headers=employee_headers)
    assert case_id in [c["id"] for c in r.json()["data"]]
    r = await client.get("/api/v1/loan-cases?status=credit_evaluation", headers=employee_headers)
    assert case_id not in [c["id"] for c in r.json()["data"]]


async def test_valid_insurance_status_update_persists_and_reflects_in_list(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _customer_headers, _application_id = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000002")

    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "policy_document"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"

    r = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "policy_document"

    r = await client.get("/api/v1/insurance-cases?status=policy_document", headers=employee_headers)
    assert case_id in [c["id"] for c in r.json()["data"]]
    r = await client.get("/api/v1/insurance-cases?status=fresh_lead", headers=employee_headers)
    assert case_id not in [c["id"] for c in r.json()["data"]]


# ---------------------------------------------------------------------- 2/4: cross-case-type / invalid status rejected


async def test_loan_status_endpoint_rejects_insurance_only_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000003")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "policy_document"}, headers=employee_headers)
    assert r.status_code == 422, r.text
    # Status must remain untouched.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "new_customer"


async def test_insurance_status_endpoint_rejects_loan_only_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000004")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 422, r.text
    r = await client.get(f"/api/v1/insurance-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "fresh_lead"


async def test_loan_status_endpoint_rejects_nonsense_status_value(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000005")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "not_a_real_status"}, headers=employee_headers)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- 5/6: unauthorized rejected


async def test_unauthorized_employee_cannot_update_loan_status(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000006")
    await _create_employee(client, owner_headers, master_data, mobile="9711100006", email="bystander-loan@example.com")
    bystander_headers = await _login(client, "9711100006")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=bystander_headers)
    assert r.status_code == 403, r.text


async def test_unauthorized_employee_cannot_update_insurance_status(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000007")
    await _create_employee(client, owner_headers, master_data, mobile="9711100007", email="bystander-ins@example.com")
    bystander_headers = await _login(client, "9711100007")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "policy_document"}, headers=bystander_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- 7: non-existent case -> 404


async def test_status_update_on_nonexistent_loan_case_returns_404(client, owner_headers):
    r = await client.patch("/api/v1/loan-cases/000000000000000000000000/status", json={"status": "credit_evaluation"}, headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_status_update_on_nonexistent_insurance_case_returns_404(client, owner_headers):
    r = await client.patch("/api/v1/insurance-cases/000000000000000000000000/status", json={"status": "policy_document"}, headers=owner_headers)
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

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)
    status_entries = [e for e in r.json()["data"] if e["type"] == "status"]
    entry = next(e for e in status_entries if e["to_status"] == "credit_evaluation")
    assert entry["from_status"] == "new_customer"
    assert entry["created_by"] is not None
    assert entry["created_at"] is not None


# ---------------------------------------------------------------------- 12: assignment/tenant isolation preserved


async def test_employee_not_assigned_to_case_is_forbidden(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000010")
    other = await _create_employee(client, owner_headers, master_data, mobile="9711100010", email="other-officer@example.com")
    await _grant_case_permission(client, owner_headers, other["id"], module="loan_management", actions=["view", "edit"])
    other_headers = await _login(client, "9711100010")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=other_headers)
    assert r.status_code == 403, r.text  # this case isn't assigned to them


# ---------------------------------------------------------------------- 13/14: Customer Portal reflects the live status


async def test_customer_portal_reflects_updated_loan_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _application_id = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000011")

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.json()["data"]["current_status"] == "new_customer"

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"  # must not still show the old status


async def test_customer_portal_reflects_updated_insurance_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _application_id = await _insurance_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000012")

    r = await client.get(f"/api/v1/insurance-cases/mine/{case_id}", headers=customer_headers)
    assert r.json()["data"]["current_status"] == "fresh_lead"

    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/status", json={"status": "policy_document"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/insurance-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"


async def test_customer_application_timeline_reflects_updated_loan_status(client, mock_db, owner_headers, master_data):
    """The Customer Portal's actual status display (ApplicationTimelinePage.tsx) reads
    `GET /applications/{id}/timeline`, which marks whichever WorkflowDefinition matches
    the case's live `current_status` as "current" — not a second, independently-tracked
    Application status. This is the concrete customer-facing surface §9 requires."""
    case_id, employee_headers, customer_headers, application_id = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000013")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/applications/{application_id}/timeline", headers=customer_headers)
    assert r.status_code == 200, r.text
    current_entries = [e for e in r.json()["data"] if e.get("state") == "current"]
    assert any(e["label"] == "Credit Evaluation" for e in current_entries)


# ---------------------------------------------------------------------- existing business rules preserved through the generic control


async def test_verify_documents_dedicated_action_still_enforces_upload_precondition(client, mock_db, owner_headers, master_data):
    """Production redesign (decision #129): `request_documents` at New Customer no
    longer auto-transitions into a "Documents Pending" status (retired from the
    mandatory pipeline — a Lead only reaches Loan Management once its required
    documents are already verified, decision #127) — it just records which document
    types are outstanding, and the case stays at `new_customer`. The dedicated
    `/documents/verify` action still enforces its own precondition (every requested
    document must actually be uploaded) when staff chooses to use it."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000014")

    extra_doc = DocumentType(name="Extra Required Doc")
    extra_doc_id = str((await mock_db["document_types"].insert_one(extra_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/request", json={"document_type_ids": [extra_doc_id]}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "new_customer"  # no longer auto-transitions

    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/verify", headers=employee_headers)
    assert r.status_code == 422, r.text  # extra_doc was never uploaded
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "new_customer"  # unchanged

    # Neither the New Customer dedicated action (decision #132) nor the generic plain
    # status control are gated on any outstanding document request — both remain usable
    # regardless, confirmed business requirement (decision #129).
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"


async def test_generic_status_update_rejects_transition_requiring_dedicated_action(client, mock_db, owner_headers, master_data):
    """credit_evaluation -> offer_acceptance requires selecting an Approved bank offer
    (decision #129) the generic {"status": ...} body can't carry — must be rejected, not
    silently executed with no offer selected."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000015")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
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
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"


# ---------------------------------------------------------------------- RV / OV / Ref (decision #130)


async def _advance_to_rv_ov_ref(client, case_id, employee_headers):
    """Drives a fresh case (new_customer) through Credit Evaluation/Offer Acceptance to
    Additional Documents, then the still-plain `additional_documents -> rv_ov_ref` move —
    the same sequence `test_loan_bank_offers.py` already exercises."""
    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000, "emi_per_month": 18500},
        headers=employee_headers,
    )
    offer_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rv_ov_ref"


_RV_OV_REF_PAYLOAD = {
    "rv_ov_ref_type": "Residence Verification",
    "rv_ov_ref_status": "completed",
    "rv_ov_ref_date": "2026-08-20T00:00:00Z",
    "rv_ov_ref_verified_by": "Field Agent Kumar",
    "rv_ov_ref_result": "positive",
    "rv_ov_ref_remarks": "Address confirmed, customer present.",
}


async def test_rv_ov_ref_records_data_and_transitions(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000018")
    await _advance_to_rv_ov_ref(client, case_id, employee_headers)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/rv-ov-ref", json=_RV_OV_REF_PAYLOAD, headers=employee_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["current_status"] == "esign_nach_kyc"
    assert data["loan_details"]["rv_ov_ref_type"] == "Residence Verification"
    assert data["loan_details"]["rv_ov_ref_status"] == "completed"
    assert data["loan_details"]["rv_ov_ref_verified_by"] == "Field Agent Kumar"
    assert data["loan_details"]["rv_ov_ref_result"] == "positive"
    assert data["loan_details"]["rv_ov_ref_remarks"] == "Address confirmed, customer present."

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["loan_details"]["rv_ov_ref_type"] == "Residence Verification"


async def test_rv_ov_ref_rejected_via_plain_status_control(client, mock_db, owner_headers, master_data):
    """`(rv_ov_ref, esign_nach_kyc)` no longer bodiless — it now carries mandatory
    verification data, so the generic control must reject it, same as every other
    dedicated-action-only move (decision #130)."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000019")
    await _advance_to_rv_ov_ref(client, case_id, employee_headers)

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "esign_nach_kyc"}, headers=employee_headers)
    assert r.status_code == 409, r.text
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "rv_ov_ref"


async def test_rv_ov_ref_requires_current_status_rv_ov_ref(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000020")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/rv-ov-ref", json=_RV_OV_REF_PAYLOAD, headers=employee_headers)
    assert r.status_code == 409, r.text  # still at new_customer


async def test_rv_ov_ref_requires_edit_permission(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000021")
    await _advance_to_rv_ov_ref(client, case_id, employee_headers)

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9800000021", email="bystander21@example.com")
    await _grant_case_permission(client, owner_headers, bystander["id"], module="loan_management", actions=["view"])
    bystander_headers = await _login(client, "9800000021")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/rv-ov-ref", json=_RV_OV_REF_PAYLOAD, headers=bystander_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- New Customer (decision #132)


async def test_new_customer_details_saves_fields_and_transitions(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000022")

    payload = {
        "preferred_bank_name": "HDFC Bank", "preferred_branch": "MG Road", "loan_type": "Personal Loan",
        "requested_amount": 500000, "preferred_remarks": "Customer prefers HDFC due to existing relationship.",
    }
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json=payload, headers=employee_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["current_status"] == "credit_evaluation"
    assert data["loan_details"]["preferred_bank_name"] == "HDFC Bank"
    assert data["loan_details"]["preferred_branch"] == "MG Road"
    assert data["loan_details"]["loan_type"] == "Personal Loan"
    assert data["loan_details"]["requested_amount"] == 500000
    assert data["loan_details"]["preferred_remarks"] == "Customer prefers HDFC due to existing relationship."

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["loan_details"]["preferred_bank_name"] == "HDFC Bank"


async def test_new_customer_details_all_fields_optional(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000023")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"


async def test_new_customer_details_rejected_at_wrong_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000024")
    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 409, r.text  # already at credit_evaluation


async def test_new_customer_details_requires_edit_permission(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000025")

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9800000025", email="bystander25@example.com")
    await _grant_case_permission(client, owner_headers, bystander["id"], module="loan_management", actions=["view"])
    bystander_headers = await _login(client, "9800000025")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=bystander_headers)
    assert r.status_code == 403, r.text


async def test_new_customer_to_credit_evaluation_plain_transition_now_rejected(client, mock_db, owner_headers, master_data):
    """Regression guard for decision #132's core fix: the old one-click,
    zero-data-required bug (`new_customer -> credit_evaluation` as a bodiless
    `_PLAIN_TRANSITIONS` move) must stay closed — this pair now requires the dedicated
    `new-customer-details` action."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000026")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 409, r.text
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "new_customer"  # unchanged


# ---------------------------------------------------------------------- bank offer additive fields


async def test_bank_offer_additive_fields_round_trip(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000027")
    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={
            "bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000,
            "interest_rate": 11.5, "tenure_months": 60, "processing_fee": 5000, "emi_per_month": 17400,
        },
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    offer_id = r.json()["data"]["id"]
    assert r.json()["data"]["interest_rate"] == 11.5
    assert r.json()["data"]["tenure_months"] == 60
    assert r.json()["data"]["processing_fee"] == 5000
    assert r.json()["data"]["emi_per_month"] == 17400

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    offer = next(o for o in r.json()["data"] if o["id"] == offer_id)
    assert offer["interest_rate"] == 11.5
    assert offer["tenure_months"] == 60
    assert offer["processing_fee"] == 5000
    assert offer["emi_per_month"] == 17400

    r = await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={
            "bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000,
            "interest_rate": 10.75, "tenure_months": 48, "processing_fee": 4500, "emi_per_month": 20600,
        },
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["interest_rate"] == 10.75
    assert r.json()["data"]["tenure_months"] == 48
    assert r.json()["data"]["processing_fee"] == 4500
    assert r.json()["data"]["emi_per_month"] == 20600

    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["loan_details"]["offered_interest_rate"] == 10.75
    assert r.json()["data"]["loan_details"]["offered_tenure_months"] == 48


# ---------------------------------------------------------------------- tab-count / list consistency (spec §23)


async def test_counts_match_list_totals_for_owner(client, mock_db, owner_headers, master_data):
    """Base case (no search/unassigned_only narrowing): the counts endpoint and the
    matching status-filtered list must always agree, for every status a case can reach."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000028")

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["new_customer"] == 1
    listed = (await client.get("/api/v1/loan-cases?status=new_customer&page_size=100", headers=owner_headers)).json()["data"]
    assert len(listed) == counts["new_customer"]
    assert case_id in {c["id"] for c in listed}

    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["new_customer"] == 0
    assert counts["credit_evaluation"] == 1
    listed_new_customer = (await client.get("/api/v1/loan-cases?status=new_customer&page_size=100", headers=owner_headers)).json()["data"]
    assert len(listed_new_customer) == counts["new_customer"] == 0
    listed_credit_eval = (await client.get("/api/v1/loan-cases?status=credit_evaluation&page_size=100", headers=owner_headers)).json()["data"]
    assert len(listed_credit_eval) == counts["credit_evaluation"] == 1
    assert case_id in {c["id"] for c in listed_credit_eval}


async def test_counts_match_list_totals_for_assigned_employee(client, mock_db, owner_headers, master_data):
    """Same consistency guarantee scoped to an Employee actor (assigned_to-filtered)."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000029")
    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)

    counts = (await client.get("/api/v1/loan-cases/counts", headers=employee_headers)).json()["data"]
    assert counts["credit_evaluation"] == 1
    listed = (await client.get("/api/v1/loan-cases?status=credit_evaluation&page_size=100", headers=employee_headers)).json()["data"]
    assert len(listed) == counts["credit_evaluation"] == 1
    assert case_id in {c["id"] for c in listed}


async def test_search_narrows_list_below_tab_badge_without_changing_the_badge(client, mock_db, owner_headers, master_data):
    """A search box narrowing the visible list is legitimate (identical in kind to the
    already-accepted "Unassigned Cases only" narrowing) — but the tab badge itself must
    keep reporting the stage's real total, and the list's own returned total (meta,
    not the badge) must reflect only what actually matches the search, never the
    global tab count."""
    case_id_1, _e1, _c1, _a1 = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000030")
    case_id_2, _e2, _c2, _a2 = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000031")

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["new_customer"] == 2

    all_new_customer = (await client.get("/api/v1/loan-cases?status=new_customer&page_size=100", headers=owner_headers)).json()
    assert len(all_new_customer["data"]) == 2
    assert all_new_customer["meta"]["pagination"]["total"] == 2
    code_1 = next(c["case_code"] for c in all_new_customer["data"] if c["id"] == case_id_1)

    r = await client.get(f"/api/v1/loan-cases?status=new_customer&page_size=100&search={code_1}", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == case_id_1
    # The search-scoped list's own total must equal its own filtered result count -
    # never the unfiltered tab badge (still 2).
    assert body["meta"]["pagination"]["total"] == 1
    assert body["meta"]["pagination"]["total"] != counts["new_customer"]

    # The badge itself is untouched by the search — it still reports the real stage total.
    counts_after_search = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts_after_search["new_customer"] == 2


async def test_pagination_total_matches_filtered_query_not_the_tab_badge(client, mock_db, owner_headers, master_data):
    """Pagination must run against the exact same filtered query the count was built
    from - `meta.pagination.total` on a status-filtered page is the count of that
    filtered query, and stays correct (and distinct from the global badge) once an
    `assigned_to` filter is layered on top of the status filter."""
    case_id_1, employee_headers, _c1, _a1 = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000032")
    case_id_2, _e2, _c2, _a2 = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000033")
    await client.post(f"/api/v1/loan-cases/{case_id_1}/new-customer-details", json={}, headers=employee_headers)

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["new_customer"] == 1  # only case 2 remains at New Customer
    assert counts["credit_evaluation"] == 1

    r = await client.get("/api/v1/loan-cases?status=new_customer&page_size=1&page=1", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == case_id_2
    assert body["meta"]["pagination"]["total"] == 1
    assert body["meta"]["pagination"]["total_pages"] == 1

    r = await client.get("/api/v1/loan-cases?status=new_customer&page_size=1&page=2", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 0
    assert body["meta"]["pagination"]["total"] == 1  # unchanged by an out-of-range page

    # Layering assigned_to on top of status must scope the total to the intersection,
    # not silently fall back to either filter alone.
    employee_1_id = (await client.get(f"/api/v1/loan-cases/{case_id_1}", headers=owner_headers)).json()["data"]["assigned_to"]
    r = await client.get(
        f"/api/v1/loan-cases?status=credit_evaluation&assigned_to={employee_1_id}&page_size=100", headers=owner_headers
    )
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == case_id_1
    assert body["meta"]["pagination"]["total"] == 1


async def test_credit_evaluation_badge_matches_list_exactly(client, mock_db, owner_headers, master_data):
    """The literal production report: 'Credit Evaluation (4)' badge, but clicking the
    tab showed 0 results. Confirms this specific stage (reached via the real
    new-customer-details action, not a synthetic status write) has no backend
    count/list divergence — the actual production root cause was a frontend
    tab-navigation bug (see CaseListPage.test.tsx), not this query."""
    case_ids = []
    for i in range(4):
        case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix=f"0000010{i}")
        await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
        case_ids.append(case_id)

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["credit_evaluation"] == 4

    r = await client.get("/api/v1/loan-cases?status=credit_evaluation&page_size=100", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 4
    assert body["meta"]["pagination"]["total"] == 4
    assert {c["id"] for c in body["data"]} == set(case_ids)


async def test_offer_acceptance_badge_matches_list_exactly(client, mock_db, owner_headers, master_data):
    """Same literal report for the 'Offer Acceptance (1)' badge — reached via the real
    bank-offer-selection action."""
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000105")
    await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000, "emi_per_month": 18500},
        headers=employee_headers,
    )
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "offer_acceptance"

    counts = (await client.get("/api/v1/loan-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["offer_acceptance"] == 1
    assert counts["credit_evaluation"] == 0

    r = await client.get("/api/v1/loan-cases?status=offer_acceptance&page_size=100", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 1
    assert body["meta"]["pagination"]["total"] == 1
    assert body["data"][0]["id"] == case_id

    # And the now-empty Credit Evaluation tab genuinely has zero matching cases (not a
    # hidden non-zero list contradicting its own zero badge).
    r = await client.get("/api/v1/loan-cases?status=credit_evaluation&page_size=100", headers=owner_headers)
    body = r.json()
    assert len(body["data"]) == 0
    assert body["meta"]["pagination"]["total"] == 0


# ---------------------------------------------------------------------- Staff Override — Skip Stage Validations (Loan only)


async def test_staff_override_moves_loan_case_to_any_stage_skipping_gates(client, mock_db, owner_headers, master_data):
    # A brand-new case sits at `new_customer` with no bank offer, no documents, no
    # credit evaluation — every normal gate to Offer Acceptance / eSign is unmet.
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000020")

    # Normal control still refuses the non-adjacent jump.
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "esign_nach_kyc"}, headers=employee_headers)
    assert r.status_code in (409, 422)

    # Staff Override moves it straight there.
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/override-stage",
        json={"status": "esign_nach_kyc", "reason": "Management approved direct movement"},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "esign_nach_kyc"

    # Audit + history record the override.
    timeline = (await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)).json()["data"]
    assert any(e.get("to_status") == "esign_nach_kyc" for e in timeline)
    assert any("Staff override" in (e.get("text") or "") for e in timeline)
    audit = [
        d async for d in mock_db["audit_logs"].find({"event_type": "loan_case_staff_override_stage_move"})
    ]
    assert len(audit) == 1
    assert audit[0]["metadata"]["override"] is True
    assert audit[0]["metadata"]["from_status"] == "new_customer"
    assert audit[0]["metadata"]["to_status"] == "esign_nach_kyc"


async def test_staff_override_reason_is_optional_and_reject_sets_rejection_reason(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000021")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/override-stage", json={"status": "disbursed"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "disbursed"

    r = await client.post(f"/api/v1/loan-cases/{case_id}/override-stage", json={"status": "rejected"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["rejection_reason"]  # a placeholder reason is recorded


async def test_staff_override_rejects_on_hold_and_bad_status(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000022")

    for bad in ("on_hold", "policy_document", "not_a_status"):
        r = await client.post(f"/api/v1/loan-cases/{case_id}/override-stage", json={"status": bad}, headers=employee_headers)
        assert r.status_code == 422, (bad, r.text)


async def test_staff_override_requires_edit_permission(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000023")
    await _create_employee(client, owner_headers, master_data, mobile="9711100023", email="bystander-ovr@example.com")
    bystander_headers = await _login(client, "9711100023")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/override-stage", json={"status": "disbursed"}, headers=bystander_headers)
    assert r.status_code == 403, r.text


async def test_staff_override_does_not_change_normal_flow(client, mock_db, owner_headers, master_data):
    # The normal adjacent move + its gate are completely unaffected by the new endpoint.
    case_id, employee_headers, _c, _a = await _loan_case(client, mock_db, owner_headers, master_data, mobile_suffix="00000024")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"
