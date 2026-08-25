"""Tests for the Loan Management Workflow & Complete Application View redesign:
New Customer's multi-record bank/NBFC capture, EMI, named Additional Documents,
Reject/Move Back on the newly-enabled statuses, and the Loan Management View's
customer/application/bank_offers blocks. `test_loan_bank_offers.py`/
`test_case_status_control.py`/`test_workflow.py` cover everything that predates this
round; this file is scoped to what's genuinely new.
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.system_settings.models import DocumentType, LoanProduct
from app.features.workflow_engine.constants import ON_HOLD_STATUS, CaseType, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition

# Mirrors scripts/seed.py's current loan_rows exactly (allowed_next_statuses +
# allowed_previous_statuses) — must be kept in sync with that file by hand, same
# accepted convention every other test file in this suite already follows for its own
# local `_seed_workflow_definitions`.
_LOAN_ROWS = [
    (LoanStatus.NEW_CUSTOMER, "New Customer", 1, [LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED], [], LoanAuditEvent.CASE_CREATED),
    (
        LoanStatus.CREDIT_EVALUATION, "Credit Evaluation", 2,
        [LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED, LoanStatus.RE_ELIGIBLE], [LoanStatus.NEW_CUSTOMER], LoanAuditEvent.CREDIT_EVALUATED,
    ),
    (
        LoanStatus.OFFER_ACCEPTANCE, "Offer Acceptance", 3, [LoanStatus.ADDITIONAL_DOCUMENTS, LoanStatus.REJECTED],
        [LoanStatus.CREDIT_EVALUATION], LoanAuditEvent.BANK_OFFER_SELECTED,
    ),
    (
        LoanStatus.ADDITIONAL_DOCUMENTS, "Additional Documents", 4, [LoanStatus.RV_OV_REF, LoanStatus.REJECTED],
        [LoanStatus.OFFER_ACCEPTANCE], LoanAuditEvent.OFFER_ACCEPTED,
    ),
    (
        LoanStatus.RV_OV_REF, "RV/OV/Ref", 5, [LoanStatus.ESIGN_NACH_KYC, LoanStatus.REJECTED],
        [LoanStatus.ADDITIONAL_DOCUMENTS], LoanAuditEvent.ADDITIONAL_DOCS_VERIFIED,
    ),
    (
        LoanStatus.ESIGN_NACH_KYC, "eSign / NACH / KYC", 6, [LoanStatus.FINAL_EVALUATION, LoanStatus.REJECTED],
        [LoanStatus.RV_OV_REF], LoanAuditEvent.RV_OV_REF_COMPLETED,
    ),
    (
        LoanStatus.FINAL_EVALUATION, "Final Evaluation", 7, [LoanStatus.SEND_FOR_DISBURSEMENT, LoanStatus.REJECTED],
        [LoanStatus.ESIGN_NACH_KYC], LoanAuditEvent.ESIGN_NACH_KYC_COMPLETED,
    ),
    (
        LoanStatus.SEND_FOR_DISBURSEMENT, "Send For Disbursement", 8, [LoanStatus.DISBURSED, LoanStatus.REJECTED],
        [LoanStatus.FINAL_EVALUATION], LoanAuditEvent.FINAL_EVALUATED,
    ),
    (LoanStatus.DISBURSED, "Disbursed", 9, [], [], LoanAuditEvent.DISBURSED),
    (LoanStatus.RE_ELIGIBLE, "Re-Eligible", 10, [LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED], [], LoanAuditEvent.MARKED_RE_ELIGIBLE),
    (LoanStatus.REJECTED, "Application Rejected", 11, [], [], LoanAuditEvent.REJECTED),
]


async def _seed_workflow_definitions(mock_db):
    for status, label, sequence, allowed_next, allowed_previous, audit_event in _LOAN_ROWS:
        full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status != LoanStatus.DISBURSED and status != LoanStatus.REJECTED else allowed_next
        definition = WorkflowDefinition(
            case_type=CaseType.LOAN, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next,
            allowed_previous_statuses=allowed_previous, audit_event=audit_event,
        )
        await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))
    on_hold_definition = WorkflowDefinition(
        case_type=CaseType.LOAN, status=ON_HOLD_STATUS, label="On Hold", sequence=len(_LOAN_ROWS) + 1,
        allowed_next_statuses=list(LoanStatus.RESUMABLE), audit_event="workflow_case_on_hold",
    )
    await mock_db["workflow_definitions"].insert_one(on_hold_definition.model_dump(by_alias=True, exclude={"id"}))


async def _seed_product_and_form(mock_db, *, product_name="Personal Loan"):
    product = LoanProduct(name=product_name)
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    pan = DocumentType(name=f"PAN-{product_name}")
    pan_id = (await mock_db["document_types"].insert_one(pan.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    form_def = ApplicationFormDefinition(
        product_category="loan", product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=str(pan_id))], status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return {"product_category": "loan", "product_id": str(product_id), "document_type_id": str(pan_id)}


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
    r = await client.post("/api/v1/customers/me", json={"full_name": "Redesign Test Customer"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": product["product_id"]}, headers=customer_headers)
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 100000}}, headers=customer_headers)
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf"},
        headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "doc.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers, application_id


async def _grant_case_permission(client, owner_headers, employee_id, *, actions):
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    permission = next((p for p in existing.json()["data"] if p["module"] == "loan_management" and p["resource"] == "applications"), None)
    if permission is None:
        r = await client.post("/api/v1/permissions", json={"module": "loan_management", "resource": "applications", "actions": actions}, headers=owner_headers)
        assert r.status_code == 200, r.text
        permission = r.json()["data"]
    r = await client.post("/api/v1/roles", json={"name": f"Redesign Role {employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, *, mobile_suffix):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, product_name=f"Redesign Loan {mobile_suffix}")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile=f"96{mobile_suffix}")
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    employee = await _create_employee(client, owner_headers, master_data, mobile=f"97{mobile_suffix}", email=f"redesign{mobile_suffix}@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], actions=["view", "edit", "approve", "assign"])
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    employee_headers = await _login(client, f"97{mobile_suffix}")
    return case_id, employee_headers, customer_headers, application_id


# ---------------------------------------------------------------------- New Customer bank/NBFC capture


async def test_bank_offer_can_be_added_edited_deleted_at_new_customer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000001")

    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={"bank_name": "HDFC", "branch": "Bangalore", "loan_type": "Personal Loan", "requested_amount": 250000, "remarks": "First pass"},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    offer = r.json()["data"]
    assert offer["decision"] == "pending"
    assert offer["branch"] == "Bangalore"
    offer_id = offer["id"]

    # Persists across a simulated "refresh" (re-fetch).
    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={"bank_name": "HDFC", "branch": "Koramangala", "loan_type": "Personal Loan", "requested_amount": 250000},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["branch"] == "Koramangala"

    r = await client.delete(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}", headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    assert r.json()["data"] == []


async def test_move_to_credit_evaluation_requires_at_least_one_bank_offer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000002")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)
    assert r.status_code == 422, r.text

    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC"}, headers=employee_headers)
    r = await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"

    # The SAME bank record survives the transition unchanged — never asked to re-enter.
    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["bank_name"] == "HDFC"


async def test_emi_required_when_approved_and_round_trips(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000003")
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC"}, headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)
    offer_id = (await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)).json()["data"][0]["id"]

    r = await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={"bank_name": "HDFC", "decision": "approved", "approved_amount": 230000},
        headers=employee_headers,
    )
    assert r.status_code == 422, r.text

    r = await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={"bank_name": "HDFC", "decision": "approved", "approved_amount": 230000, "interest_rate": 1.5, "tenure_months": 24, "emi_per_month": 11200},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["emi_per_month"] == 11200


# ---------------------------------------------------------------------- Additional Documents


async def _advance_case_to_additional_documents(client, mock_db, owner_headers, master_data, *, mobile_suffix):
    case_id, employee_headers, customer_headers, application_id = await _loan_case_at_new_customer(
        client, mock_db, owner_headers, master_data, mobile_suffix=mobile_suffix
    )
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC"}, headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)
    offer_id = (await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)).json()["data"][0]["id"]
    await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={"bank_name": "HDFC", "decision": "approved", "approved_amount": 230000, "emi_per_month": 11200},
        headers=employee_headers,
    )
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    return case_id, employee_headers, customer_headers, application_id


async def test_additional_document_full_lifecycle(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _a = await _advance_case_to_additional_documents(
        client, mock_db, owner_headers, master_data, mobile_suffix="10000004"
    )

    r = await client.post(f"/api/v1/loan-cases/{case_id}/additional-documents", json={"name": "Salary Revision Letter"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    doc_id = r.json()["data"]["id"]
    assert r.json()["data"]["document_status"] == "requested"

    # Customer sees the exact requested name.
    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}/additional-documents", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"][0]["name"] == "Salary Revision Letter"

    # Blocked from advancing while the document is still outstanding.
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    assert r.status_code == 422, r.text

    # Customer uploads it.
    r = await client.post(
        f"/api/v1/loan-cases/mine/{case_id}/additional-documents/{doc_id}/upload-url", json={"file_name": "letter.pdf"}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    s3_key = r.json()["data"]["s3_key"]
    r = await client.post(
        f"/api/v1/loan-cases/mine/{case_id}/additional-documents/{doc_id}/confirm",
        json={"file_name": "letter.pdf", "s3_key": s3_key}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "uploaded"

    # Staff now sees it uploaded.
    r = await client.get(f"/api/v1/loan-cases/{case_id}/additional-documents", headers=employee_headers)
    assert r.json()["data"][0]["document_status"] == "uploaded"

    # Reject with a reason, then verify after a fresh upload/re-review — first reject:
    r = await client.post(f"/api/v1/loan-cases/{case_id}/additional-documents/{doc_id}/reject", json={"reason": "Not clear"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "rejected"
    assert r.json()["data"]["rejection_reason"] == "Not clear"

    # Still blocked — a rejected document is not a verified one.
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    assert r.status_code == 422, r.text

    r = await client.post(f"/api/v1/loan-cases/{case_id}/additional-documents/{doc_id}/verify", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"

    # Now allowed.
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rv_ov_ref"


async def test_move_to_rv_ov_ref_allowed_when_no_additional_documents_ever_requested(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _advance_case_to_additional_documents(client, mock_db, owner_headers, master_data, mobile_suffix="10000005")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- Reject / Move Back


async def test_reject_reachable_from_new_customer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000006")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected"}, headers=employee_headers)
    assert r.status_code == 422, r.text  # reason mandatory
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "Ineligible"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"


async def test_reject_reachable_from_additional_documents(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _advance_case_to_additional_documents(client, mock_db, owner_headers, master_data, mobile_suffix="10000007")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "Customer withdrew"}, headers=employee_headers)
    assert r.status_code == 200, r.text


async def test_move_back_from_credit_evaluation_to_new_customer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000008")
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC"}, headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)

    r = await client.post(f"/api/v1/loan-cases/{case_id}/move-back", json={}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "new_customer"
    assert r.json()["data"]["allowed_previous_statuses"] == []


async def test_move_back_rejected_when_no_previous_status_configured(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000009")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/move-back", json={}, headers=employee_headers)
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------- Loan Management View — complete application


async def test_staff_detail_includes_customer_application_and_bank_offers(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000010")
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC", "branch": "Bangalore"}, headers=employee_headers)

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["customer"]["full_name"] == "Redesign Test Customer"
    assert data["application"]["application_code"].startswith("AFS-APP-")
    assert len(data["bank_offers"]) == 1
    assert data["bank_offers"][0]["bank_name"] == "HDFC"


async def test_customer_own_detail_never_leaks_staff_only_bank_offer_fields(client, mock_db, owner_headers, master_data):
    """Regression: the customer's own `/loan-cases/mine/{id}` response must never carry
    the staff-shape `bank_offers` block (assigned_officer/remarks/decision/etc are
    staff-only, decision #129) — caught and fixed during this round's implementation."""
    case_id, employee_headers, customer_headers, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000011")
    await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC", "assigned_officer": "Internal Officer", "remarks": "Internal note"},
        headers=employee_headers,
    )

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["bank_offers"] == []
    assert data["customer"] is None
    assert data["application"] is None


async def test_legacy_case_with_no_bank_offers_still_returns_full_detail(client, mock_db, owner_headers, master_data):
    """Backward compatibility (requirement 33): a case that used the OLD single-slot
    `record_new_customer_details` path and never got a bank-offer record must still
    render without crashing."""
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix="10000012")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/new-customer-details", json={"preferred_bank_name": "Legacy Bank"}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}", headers=employee_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["bank_offers"] == []
    assert data["loan_details"]["preferred_bank_name"] == "Legacy Bank"


# ---------------------------------------------------------------------- Disbursements report


async def _disburse_case(client, mock_db, owner_headers, master_data, *, mobile_suffix, approved_amount, disbursed_amount, product_name):
    case_id, employee_headers, _c, _a = await _loan_case_at_new_customer(client, mock_db, owner_headers, master_data, mobile_suffix=mobile_suffix)
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC"}, headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/move-to-credit-evaluation", json={}, headers=employee_headers)
    offer_id = (await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)).json()["data"][0]["id"]
    await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}",
        json={"bank_name": "HDFC", "decision": "approved", "approved_amount": approved_amount, "emi_per_month": 5000},
        headers=employee_headers,
    )
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rv_ov_ref"}, headers=employee_headers)
    await client.post(
        f"/api/v1/loan-cases/{case_id}/rv-ov-ref",
        json={
            "rv_ov_ref_type": "Residence Verification", "rv_ov_ref_status": "completed", "rv_ov_ref_date": "2026-08-01T00:00:00Z",
            "rv_ov_ref_verified_by": "Field Agent", "rv_ov_ref_result": "positive",
        },
        headers=employee_headers,
    )
    await client.post(
        f"/api/v1/loan-cases/{case_id}/esign-nach-kyc", json={"esign_completed": True, "nach_completed": True, "kyc_completed": True},
        headers=employee_headers,
    )
    await client.post(f"/api/v1/loan-cases/{case_id}/final-evaluation", json={"decision": "approved"}, headers=employee_headers)
    r = await client.post(
        f"/api/v1/loan-cases/{case_id}/disburse", json={"disbursed_amount": disbursed_amount, "disbursed_reference": f"REF-{mobile_suffix}"},
        headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    return case_id


async def test_disbursements_total_matches_filtered_list_and_product_filter_narrows_both(client, mock_db, owner_headers, master_data):
    await _disburse_case(
        client, mock_db, owner_headers, master_data, mobile_suffix="10000013", approved_amount=200000, disbursed_amount=200000,
        product_name="Personal Loan A",
    )
    await _disburse_case(
        client, mock_db, owner_headers, master_data, mobile_suffix="10000014", approved_amount=250000, disbursed_amount=250000,
        product_name="Personal Loan B",
    )

    r = await client.get("/api/v1/loan-cases/disbursements", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total_count"] == 2
    assert body["total_amount"] == 450000
    assert len(body["items"]) == 2
    assert all(item["disbursed_at"] is not None for item in body["items"])

    # Product filter narrows card + list together (never disagreeing, single query).
    case_id_200k = next(item["id"] for item in body["items"] if item["disbursed_amount"] == 200000)
    case_detail = await client.get(f"/api/v1/loan-cases/{case_id_200k}", headers=owner_headers)
    filter_product_id = case_detail.json()["data"]["product_id"]

    r = await client.get(f"/api/v1/loan-cases/disbursements?product_id={filter_product_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    filtered = r.json()["data"]
    assert filtered["total_count"] == 1
    assert filtered["total_amount"] == 200000


async def test_disbursements_search_and_empty_state(client, mock_db, owner_headers, master_data):
    r = await client.get("/api/v1/loan-cases/disbursements?search=NoSuchCase", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["items"] == []
    assert body["total_count"] == 0
    assert body["total_amount"] == 0


async def test_disbursements_date_range_excludes_out_of_range_case(client, mock_db, owner_headers, master_data):
    await _disburse_case(
        client, mock_db, owner_headers, master_data, mobile_suffix="10000015", approved_amount=300000, disbursed_amount=300000,
        product_name="Personal Loan C",
    )
    r = await client.get("/api/v1/loan-cases/disbursements?date_from=2020-01-01&date_to=2020-01-31", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["total_count"] == 0
    assert body["total_amount"] == 0
