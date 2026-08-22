"""End-to-end tests for Module 6C (Loan & Insurance Processing Pipeline): case
auto-creation (lazy get-or-create) once an Application is submitted, the full Loan
pipeline through Disbursed, both approved rejection exit points (Credit Evaluation and
Final Evaluation), the finalized separate Insurance lifecycle (with/without medical
verification and additional documents, decision 064), On Hold / Resume (an Optional
Status on both pipelines, decision 064), the Owner-only Unassigned queue, Access Control
permission gating (Employee denied without a grant, allowed once one exists, scoped to
their own assignment), and reassignment auditing.
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.system_settings.models import DocumentType, InsuranceProduct, LoanProduct
from app.features.workflow_engine.constants import (
    ON_HOLD_STATUS,
    CaseType,
    InsuranceAuditEvent,
    InsuranceStatus,
    LoanAuditEvent,
    LoanStatus,
    WorkflowAuditEvent,
)
from app.features.workflow_engine.models import WorkflowDefinition

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
    (LoanStatus.RE_ELIGIBLE, "Re-Eligible", 10, [LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED], LoanAuditEvent.MARKED_RE_ELIGIBLE),
    (LoanStatus.REJECTED, "Application Rejected", 11, [], LoanAuditEvent.REJECTED),
]
_INSURANCE_ROWS = [
    (InsuranceStatus.APPLICATION_SUBMITTED, "Application Submitted", 1, [InsuranceStatus.DOCUMENTS_PENDING], InsuranceAuditEvent.CASE_CREATED),
    (InsuranceStatus.DOCUMENTS_PENDING, "Documents Pending", 2, [InsuranceStatus.UNDERWRITING], InsuranceAuditEvent.DOCUMENTS_REQUESTED),
    (
        InsuranceStatus.UNDERWRITING, "Underwriting", 3,
        [InsuranceStatus.MEDICAL_VERIFICATION, InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED],
        InsuranceAuditEvent.DOCUMENTS_VERIFIED,
    ),
    (
        InsuranceStatus.MEDICAL_VERIFICATION, "Medical Verification", 4,
        [InsuranceStatus.ADDITIONAL_DOCUMENTS, InsuranceStatus.PREMIUM_ACCEPTANCE, InsuranceStatus.REJECTED], InsuranceAuditEvent.MEDICAL_VERIFICATION_REQUIRED,
    ),
    (InsuranceStatus.ADDITIONAL_DOCUMENTS, "Additional Documents", 5, [InsuranceStatus.PREMIUM_ACCEPTANCE], InsuranceAuditEvent.ADDITIONAL_DOCUMENTS_REQUIRED),
    (InsuranceStatus.PREMIUM_ACCEPTANCE, "Premium Acceptance", 6, [InsuranceStatus.POLICY_GENERATION, InsuranceStatus.REJECTED], InsuranceAuditEvent.PREMIUM_READY),
    (InsuranceStatus.POLICY_GENERATION, "Policy Generation", 7, [InsuranceStatus.POLICY_ISSUED], InsuranceAuditEvent.PREMIUM_ACCEPTED),
    (InsuranceStatus.POLICY_ISSUED, "Policy Issued", 8, [], InsuranceAuditEvent.POLICY_ISSUED),
    (InsuranceStatus.REJECTED, "Application Rejected", 9, [], InsuranceAuditEvent.REJECTED),
]


async def _seed_workflow_definitions(mock_db):
    # Mirrors scripts/seed.py:seed_workflow_definitions — tests run against a fresh
    # mongomock database, not the seed script, so this data must be inserted directly.
    for case_type, rows, resumable in ((CaseType.LOAN, _LOAN_ROWS, LoanStatus.RESUMABLE), (CaseType.INSURANCE, _INSURANCE_ROWS, InsuranceStatus.RESUMABLE)):
        for status, label, sequence, allowed_next, audit_event in rows:
            full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status in resumable else allowed_next
            definition = WorkflowDefinition(case_type=case_type, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next, audit_event=audit_event)
            await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))
        on_hold_definition = WorkflowDefinition(
            case_type=case_type, status=ON_HOLD_STATUS, label="On Hold", sequence=len(rows) + 1,
            allowed_next_statuses=list(resumable), audit_event=WorkflowAuditEvent.CASE_ON_HOLD,
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
        product_category=category,
        product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=str(pan_id))],
        status="active",
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


async def _grant_case_permission(client, owner_headers, employee_id, *, module, actions):
    r = await client.post("/api/v1/permissions", json={"module": module, "resource": "applications", "actions": actions}, headers=owner_headers)
    assert r.status_code == 200, r.text
    permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Role for {module}"}, headers=owner_headers)
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


async def _submitted_application(client, mock_db, product, *, mobile, extra_doc_ids=None):
    """Direct-portal registration -> profile -> application -> upload required doc ->
    submit. Returns (customer_headers, application_id)."""
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])

    r = await client.post("/api/v1/customers/me", json={"full_name": "Workflow Test Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]

    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 100000}}, headers=customer_headers)

    for doc_type_id in [product["document_type_id"], *(extra_doc_ids or [])]:
        upload = await client.post(
            f"/api/v1/applications/{application_id}/documents/upload-url",
            json={"document_type_id": doc_type_id, "file_name": "doc.pdf"}, headers=customer_headers,
        )
        assert upload.status_code == 200, upload.text
        s3_key = upload.json()["data"]["s3_key"]
        confirm = await client.post(
            f"/api/v1/applications/{application_id}/documents",
            json={"document_type_id": doc_type_id, "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
        )
        assert confirm.status_code == 200, confirm.text

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "submitted"
    return customer_headers, application_id


# ---------------------------------------------------------------------- Loan: happy path to Disbursed


async def test_loan_pipeline_happy_path_to_disbursed(client, mock_db, owner_headers, master_data):
    """Decision #129's redesigned pipeline, end to end: New Customer -> Credit Evaluation
    (plain, no document gate — a Lead only reaches Loan Management once its required
    documents are already verified, decision #127) -> multiple bank offers, only the
    selected one carried forward -> Offer Acceptance (select, then a separate explicit
    confirm) -> Additional Documents -> RV/OV/Ref -> eSign/NACH/KYC -> Final Evaluation ->
    Send For Disbursement -> Disbursed."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Personal Loan")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000001")

    # Case is lazily synced into existence the first time the Owner looks.
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    cases = [c for c in r.json()["data"] if c["application_id"] == application_id]
    assert len(cases) == 1
    case_id = cases[0]["id"]
    assert cases[0]["current_status"] == "new_customer"

    employee = await _create_employee(client, owner_headers, master_data, mobile="9611111111", email="loan.officer@example.com")
    employee_headers = await _login(client, "9611111111", "InitialPass1!")

    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view", "edit", "approve", "reject", "assign"])

    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "new_customer"

    # New Customer -> Credit Evaluation (plain, generic status control)
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    # Multiple bank offers — adding one never overwrites another.
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 90000}, headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    hdfc_offer_id = r.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "ICICI Bank", "decision": "rejected_re_eligible"}, headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    icici_offer_id = r.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "Axis Bank", "decision": "approved", "approved_amount": 75000}, headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    axis_offer_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    assert r.status_code == 200, r.text
    offers = r.json()["data"]
    assert {o["id"] for o in offers} == {hdfc_offer_id, icici_offer_id, axis_offer_id}  # all three retained

    # Credit Evaluation -> Offer Acceptance (select the HDFC offer)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{hdfc_offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "offer_acceptance"
    assert r.json()["data"]["loan_details"]["offered_amount"] == 90000
    assert r.json()["data"]["selected_bank_name"] == "HDFC Bank"

    # Selecting alone must NOT auto-advance past Offer Acceptance.
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "offer_acceptance"

    # Offer Acceptance -> Additional Documents requires the separate, explicit confirm step.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "additional_documents"

    salary_doc = DocumentType(name="Salary Slip (workflow test)")
    salary_doc_id = str((await mock_db["document_types"].insert_one(salary_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/request", json={"document_type_ids": [salary_doc_id]}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "additional_documents"  # no transition — optional, non-pipeline-driving

    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": salary_doc_id, "file_name": "salary.pdf"}, headers=customer_headers
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents", json={"document_type_id": salary_doc_id, "file_name": "salary.pdf", "s3_key": s3_key}, headers=customer_headers
    )

    # Additional Documents -> RV/OV/Ref
    r = await client.post(f"/api/v1/loan-cases/{case_id}/documents/verify", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rv_ov_ref"

    # RV/OV/Ref -> eSign/NACH/KYC — decision #130's dedicated action (mandatory
    # verification data, no longer a bodiless plain-control move).
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/rv-ov-ref",
        json={
            "rv_ov_ref_type": "Residence Verification", "rv_ov_ref_status": "completed", "rv_ov_ref_date": "2026-08-20T00:00:00Z",
            "rv_ov_ref_verified_by": "Field Agent", "rv_ov_ref_result": "positive", "rv_ov_ref_remarks": "Verification completed",
        },
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "esign_nach_kyc"

    r = await client.post(f"/api/v1/loan-cases/{case_id}/esign-nach-kyc", json={"esign_completed": True, "nach_completed": False, "kyc_completed": False}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "esign_nach_kyc"  # not all 3 done yet

    r = await client.post(f"/api/v1/loan-cases/{case_id}/esign-nach-kyc", json={"esign_completed": True, "nach_completed": True, "kyc_completed": True}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "final_evaluation"

    # Final Evaluation -> Send For Disbursement -> Disbursed
    r = await client.post(f"/api/v1/loan-cases/{case_id}/final-evaluation", json={"remarks": "All good", "decision": "approved"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "send_for_disbursement"

    r = await client.post(f"/api/v1/loan-cases/{case_id}/disburse", json={"disbursed_amount": 90000, "disbursed_reference": "UTR12345"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["current_status"] == "disbursed"
    assert body["loan_details"]["disbursed_amount"] == 90000
    assert body["loan_details"]["disbursed_reference"] == "UTR12345"

    # Timeline recorded every transition
    r = await client.get(f"/api/v1/loan-cases/{case_id}/timeline", headers=employee_headers)
    assert r.status_code == 200, r.text
    statuses = [e["to_status"] for e in r.json()["data"] if e["type"] == "status"]
    assert "disbursed" in statuses and "credit_evaluation" in statuses

    # Customer can see their own case throughout
    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "disbursed"


# ---------------------------------------------------------------------- Loan: rejection at both exit points


async def test_loan_rejected_at_credit_evaluation_requires_reason(client, mock_db, owner_headers):
    """Production redesign (decision #129): credit_evaluation() no longer carries a
    decision/rejection_reason (that concept moved to per-bank offers, independent of
    case status) — rejecting a case in Credit Evaluation now goes through the generic
    plain status control, which still enforces the same "reason is mandatory" rule the
    old dedicated action used to."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Business Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000002")

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected"}, headers=owner_headers)
    assert r.status_code == 422, r.text  # missing mandatory reason
    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=owner_headers)
    assert r.json()["data"]["current_status"] == "credit_evaluation"  # unchanged

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "Low credit score"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"
    assert r.json()["data"]["rejection_reason"] == "Low credit score"


async def test_loan_all_banks_rejected_moves_case_to_rejected(client, mock_db, owner_headers):
    """Spec §12: when every bank offer on a case is Rejected/Re-Eligible (no Approved
    offer exists), staff moves the case to Rejected directly — bank-level decisions and
    case-level status remain independent concepts, so this is always a deliberate staff
    action via the generic status control, never automatic."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Property Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000003")

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=owner_headers)

    for bank in ("HDFC Bank", "ICICI Bank", "Axis Bank"):
        r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": bank, "decision": "rejected_re_eligible"}, headers=owner_headers)
        assert r.status_code == 200, r.text

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "All banks declined"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"
    assert r.json()["data"]["rejection_reason"] == "All banks declined"


# ---------------------------------------------------------------------- Insurance: without and with medical


async def test_insurance_pipeline_without_medical_or_additional_docs_to_policy_issued(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="insurance", product_name="Term Life")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000004")

    r = await client.get("/api/v1/insurance-cases", headers=owner_headers)
    assert r.status_code == 200, r.text
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    assert next(c for c in r.json()["data"] if c["id"] == case_id)["current_status"] == "application_submitted"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/request", json={"document_type_ids": []}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "documents_pending"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "underwriting"

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/underwriting",
        json={"sum_insured": 500000, "requires_medical": False, "requires_additional_documents": False, "decision": "approved"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "premium_acceptance"  # both optional stages skipped

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/premium", json={"premium_amount": 5000}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/premium/accept", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_generation"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/policy/generate", json={"policy_number": "POL-0001"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_generation"  # generating doesn't itself issue
    assert r.json()["data"]["insurance_details"]["policy_number"] == "POL-0001"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/policy/issue", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_issued"
    assert r.json()["data"]["insurance_details"]["policy_issued_at"] is not None


async def test_insurance_pipeline_with_medical_and_additional_docs(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="insurance", product_name="Health Cover")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000005")

    r = await client.get("/api/v1/insurance-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/documents/request", json={"document_type_ids": []}, headers=owner_headers)
    await client.post(f"/api/v1/insurance-cases/{case_id}/documents/verify", headers=owner_headers)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/underwriting",
        json={"sum_insured": 2000000, "requires_medical": True, "requires_additional_documents": True, "decision": "approved"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "medical_verification"

    additional_doc = DocumentType(name="Additional KYC Doc")
    additional_doc_id = str((await mock_db["document_types"].insert_one(additional_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/medical-verification", json={"outcome": "cleared"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "additional_documents"  # cleared, but additional docs were also flagged

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/request", json={"document_type_ids": [additional_doc_id]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "additional_documents"  # already there — no transition, just tracked

    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": additional_doc_id, "file_name": "kyc.pdf"}, headers=customer_headers
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents", json={"document_type_id": additional_doc_id, "file_name": "kyc.pdf", "s3_key": s3_key}, headers=customer_headers
    )

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "premium_acceptance"


async def test_insurance_medical_verification_failure_rejects_case(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="insurance", product_name="Critical Illness Cover")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000015")

    r = await client.get("/api/v1/insurance-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/documents/request", json={"document_type_ids": []}, headers=owner_headers)
    await client.post(f"/api/v1/insurance-cases/{case_id}/documents/verify", headers=owner_headers)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/underwriting",
        json={"sum_insured": 2000000, "requires_medical": True, "requires_additional_documents": False, "decision": "approved"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "medical_verification"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/medical-verification", json={"outcome": "failed", "rejection_reason": "Health risk too high"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"
    assert r.json()["data"]["rejection_reason"] == "Health risk too high"


# ---------------------------------------------------------------------- On Hold / Resume (both pipelines)


async def test_loan_case_hold_and_resume(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Two Wheeler Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000016")

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/hold", json={"reason": "waiting_for_customer", "remarks": "Awaiting income proof"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "on_hold"

    # Stage-specific actions are blocked while on hold — the case genuinely paused, not just labeled.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/credit-evaluation", json={"credit_score": 750}, headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/hold", json={"reason": "internal_review"}, headers=owner_headers)
    assert r.status_code == 409, r.text  # already on hold

    r = await client.post(f"/api/v1/loan-cases/{case_id}/resume", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"  # resumed to exactly where it paused

    # And the case can now continue normally.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 60000}, headers=owner_headers)
    assert r.status_code == 200, r.text
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "offer_acceptance"

    audit_entries = [doc async for doc in mock_db["audit_logs"].find({"metadata.application_workflow_id": case_id})]
    assert any(e["event_type"] == "workflow_case_on_hold" for e in audit_entries)
    assert any(e["event_type"] == "workflow_case_resumed" for e in audit_entries)


# ---------------------------------------------------------------------- Access Control gating + reassignment audit


async def test_employee_denied_without_permission_then_scoped_once_assigned(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Gold Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000006")

    employee = await _create_employee(client, owner_headers, master_data, mobile="9622222222", email="unpermitted@example.com")
    employee_headers = await _login(client, "9622222222", "InitialPass1!")

    r = await client.get("/api/v1/loan-cases", headers=employee_headers)
    assert r.status_code == 403, r.text

    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view", "edit"])

    r = await client.get("/api/v1/loan-cases", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []  # nothing assigned to them yet

    r = await client.get("/api/v1/loan-cases", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)

    other_employee = await _create_employee(client, owner_headers, master_data, mobile="9633333333", email="other.officer@example.com")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": other_employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.status_code == 403, r.text  # assigned to the OTHER employee, not this one

    # Reassign to this employee — must be audited as a reassignment, not a fresh assignment
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    audit_entries = [doc async for doc in mock_db["audit_logs"].find({"metadata.application_workflow_id": case_id})]
    reassigned = [e for e in audit_entries if e["event_type"] == "workflow_case_reassigned"]
    assert len(reassigned) == 1

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.status_code == 200, r.text


async def test_unassigned_loan_cases_queue_is_owner_only(client, mock_db, owner_headers, master_data):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, category="loan", product_name="Vehicle Loan")
    _customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9600000007")

    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(c["application_id"] == application_id for c in r.json()["data"])

    employee = await _create_employee(client, owner_headers, master_data, mobile="9644444444", email="queue.officer@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], module="loan_management", actions=["view"])
    employee_headers = await _login(client, "9644444444", "InitialPass1!")

    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []  # unassigned_only is ignored/force-disabled for Employees
