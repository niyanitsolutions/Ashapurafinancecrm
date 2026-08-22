"""Tests for the Loan Management workflow redesign (decision #129): multi-bank-offer
support on Credit Evaluation, the Select/Confirm two-step Offer Acceptance flow,
customer-safe bank-offer trimming, the new `re_eligible`/`rv_ov_ref` statuses, and the
new `GET /loan-cases/counts` tab-badge endpoint. `test_case_status_control.py`/
`test_workflow.py` cover the generic status control and the full happy-path pipeline —
this file is scoped to what's genuinely new.
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.system_settings.models import DocumentType, LoanProduct
from app.features.workflow_engine.constants import ON_HOLD_STATUS, CaseType, LoanAuditEvent, LoanStatus
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


async def _seed_workflow_definitions(mock_db):
    for status, label, sequence, allowed_next, audit_event in _LOAN_ROWS:
        full_allowed_next = [*allowed_next, ON_HOLD_STATUS] if status != LoanStatus.DISBURSED and status != LoanStatus.REJECTED else allowed_next
        definition = WorkflowDefinition(
            case_type=CaseType.LOAN, status=status, label=label, sequence=sequence, allowed_next_statuses=full_allowed_next, audit_event=audit_event
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
    r = await client.post("/api/v1/customers/me", json={"full_name": "Bank Offer Test Customer"}, headers=customer_headers)
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
    r = await client.post("/api/v1/roles", json={"name": f"Bank Offer Role {employee_id}"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    role = r.json()["data"]
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions", json={"grants": [{"permission_id": permission["id"], "granted_actions": actions}]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/roles/{role['id']}/assign", json={"employee_id": employee_id}, headers=owner_headers)
    assert r.status_code == 200, r.text


async def _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, *, mobile_suffix):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db, product_name=f"Loan {mobile_suffix}")
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile=f"96{mobile_suffix}")
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    case_id = next(c["id"] for c in r.json()["data"] if c["application_id"] == application_id)
    employee = await _create_employee(client, owner_headers, master_data, mobile=f"97{mobile_suffix}", email=f"bankoffer{mobile_suffix}@example.com")
    await _grant_case_permission(client, owner_headers, employee["id"], actions=["view", "edit", "approve", "assign"])
    r = await client.post(f"/api/v1/loan-cases/{case_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    employee_headers = await _login(client, f"97{mobile_suffix}")
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    return case_id, employee_headers, customer_headers, application_id


# ---------------------------------------------------------------------- multiple banks, never overwritten


async def test_multiple_bank_offers_added_without_overwriting(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000101")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "ICICI Bank", "decision": "rejected_re_eligible"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "Axis Bank", "decision": "approved", "approved_amount": 750000}, headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    assert r.status_code == 200, r.text
    names = {o["bank_name"] for o in r.json()["data"]}
    assert names == {"HDFC Bank", "ICICI Bank", "Axis Bank"}


async def test_bank_offer_approved_requires_approved_amount(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000102")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved"}, headers=employee_headers)
    assert r.status_code == 422, r.text


async def test_bank_offer_rejected_re_eligible_does_not_require_approved_amount(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000103")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "rejected_re_eligible"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approved_amount"] is None


async def test_multiple_approved_offers_can_coexist(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000104")
    r1 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    r2 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "Axis Bank", "decision": "approved", "approved_amount": 750000}, headers=employee_headers)
    assert r1.status_code == 200 and r2.status_code == 200

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    approved = [o for o in r.json()["data"] if o["decision"] == "approved"]
    assert len(approved) == 2


async def test_edit_bank_offer_does_not_affect_other_offers(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000105")
    r1 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer1_id = r1.json()["data"]["id"]
    r2 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "Axis Bank", "decision": "approved", "approved_amount": 750000}, headers=employee_headers)
    offer2_id = r2.json()["data"]["id"]

    r = await client.patch(
        f"/api/v1/loan-cases/{case_id}/bank-offers/{offer1_id}",
        json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 820000}, headers=employee_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approved_amount"] == 820000

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    offer2_after = next(o for o in r.json()["data"] if o["id"] == offer2_id)
    assert offer2_after["approved_amount"] == 750000  # untouched


# ---------------------------------------------------------------------- select: staff, customer, only one at a time


async def test_staff_can_select_bank_offer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000106")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "offer_acceptance"
    assert r.json()["data"]["selected_bank_name"] == "HDFC Bank"
    assert r.json()["data"]["approved_amount"] == 800000


async def test_customer_can_select_bank_offer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000107")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/loan-cases/mine/{case_id}/bank-offers/{offer_id}/select", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "offer_acceptance"


async def test_only_one_offer_can_be_selected_at_a_time(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000108")
    r1 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer1_id = r1.json()["data"]["id"]
    r2 = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "Axis Bank", "decision": "approved", "approved_amount": 750000}, headers=employee_headers)
    offer2_id = r2.json()["data"]["id"]

    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer1_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text

    # Selecting a second offer while still in offer_acceptance is not a valid transition
    # (already left credit_evaluation) — confirms the "exactly one selected" invariant
    # can't be violated even by re-selecting from the wrong status.
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer2_id}/select", headers=employee_headers)
    assert r.status_code == 409, r.text

    r = await client.get(f"/api/v1/loan-cases/{case_id}/bank-offers", headers=employee_headers)
    selected = [o for o in r.json()["data"] if o["is_selected"]]
    assert len(selected) == 1
    assert selected[0]["id"] == offer1_id


async def test_selecting_a_non_approved_offer_is_rejected(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000109")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "ICICI Bank", "decision": "rejected_re_eligible"}, headers=employee_headers)
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- select vs. confirm are separate steps


async def test_selecting_offer_does_not_auto_confirm_acceptance(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000110")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.json()["data"]["current_status"] == "offer_acceptance"

    # Not yet confirmed — the customer's own confirm action must still be required.
    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}", headers=customer_headers)
    assert r.json()["data"]["current_status"] == "offer_acceptance"

    r = await client.post(f"/api/v1/loan-cases/mine/{case_id}/offer-acceptance/confirm", headers=customer_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "additional_documents"


async def test_confirm_offer_acceptance_requires_a_selected_offer(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000111")
    r = await client.post(f"/api/v1/loan-cases/{case_id}/offer-acceptance/confirm", headers=employee_headers)
    assert r.status_code == 409, r.text  # not even in offer_acceptance yet


# ---------------------------------------------------------------------- customer sees only safe fields


async def test_customer_sees_only_safe_bank_offer_fields(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, customer_headers, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000112")
    await client.post(
        f"/api/v1/loan-cases/{case_id}/bank-offers",
        json={
            "bank_name": "HDFC Bank", "bank_application_id": "HDFC-APP-12345", "reference_number": "REF-001",
            "assigned_officer": "Internal Officer Name", "decision": "approved", "approved_amount": 800000, "remarks": "Internal staff note",
        },
        headers=employee_headers,
    )
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "ICICI Bank", "decision": "rejected_re_eligible"}, headers=employee_headers)

    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}/bank-offers", headers=customer_headers)
    assert r.status_code == 200, r.text
    offers = r.json()["data"]
    assert len(offers) == 1  # only the approved one
    offer = offers[0]
    assert offer["bank_name"] == "HDFC Bank"
    assert offer["approved_amount"] == 800000
    assert set(offer.keys()) == {"id", "bank_name", "approved_amount"}  # no staff-only fields at all


async def test_customer_cannot_see_another_customers_bank_offers(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c1, _a1 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000113")
    await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)

    _case2, _e2, other_customer_headers, _a2 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000114")
    r = await client.get(f"/api/v1/loan-cases/mine/{case_id}/bank-offers", headers=other_customer_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- RBAC


async def test_bank_offer_endpoints_require_permission(client, mock_db, owner_headers, master_data):
    case_id, _employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000115")
    await _create_employee(client, owner_headers, master_data, mobile="9711100115", email="no-perm-bank@example.com")
    bystander_headers = await _login(client, "9711100115")

    r = await client.post(f"/api/v1/loan-cases/{case_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=bystander_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- re-eligible


async def test_re_eligible_reachable_from_credit_evaluation_and_back(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000116")

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible", "remarks": "Revisit after 90 days"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "credit_evaluation"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "credit_evaluation"


async def test_re_eligible_can_move_to_rejected(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000117")
    await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible"}, headers=employee_headers)
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "No longer pursuing"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"


async def test_rejected_case_cannot_move_directly_to_re_eligible(client, mock_db, owner_headers, master_data):
    """`REJECTED` stays terminal (decision #129) — `list_eligible_assignees` relies on
    that meaning "permanently closed" for workload balancing."""
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000118")
    await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "rejected", "remarks": "Not eligible"}, headers=employee_headers)
    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "re_eligible"}, headers=employee_headers)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- status dropdown / documents_pending retired


async def test_status_dropdown_accepts_exactly_the_twelve_statuses(client, mock_db, owner_headers, master_data):
    case_id, employee_headers, _c, _a = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000119")
    expected = {
        "new_customer", "credit_evaluation", "offer_acceptance", "additional_documents", "rv_ov_ref",
        "esign_nach_kyc", "final_evaluation", "send_for_disbursement", "disbursed", "on_hold", "re_eligible", "rejected",
    }
    assert expected == set(LoanStatus.ALL)

    r = await client.patch(f"/api/v1/loan-cases/{case_id}/status", json={"status": "documents_pending"}, headers=employee_headers)
    assert r.status_code == 422, r.text  # retired — never a valid dropdown target again


# ---------------------------------------------------------------------- counts


async def test_loan_case_counts_endpoint_reflects_current_tab_distribution(client, mock_db, owner_headers, master_data):
    case1_id, employee_headers, _c1, _a1 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000120")
    _case2_id, _e2, _c2, _a2 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000121")

    r = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert r.status_code == 200, r.text
    counts = r.json()["data"]
    assert counts["credit_evaluation"] == 2
    assert counts["new_customer"] == 0

    r = await client.post(f"/api/v1/loan-cases/{case1_id}/bank-offers", json={"bank_name": "HDFC Bank", "decision": "approved", "approved_amount": 800000}, headers=employee_headers)
    offer_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/loan-cases/{case1_id}/bank-offers/{offer_id}/select", headers=employee_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    counts = r.json()["data"]
    assert counts["credit_evaluation"] == 1  # one moved out
    assert counts["offer_acceptance"] == 1


async def test_loan_case_counts_scoped_to_assigned_employee(client, mock_db, owner_headers, master_data):
    _case1_id, employee_headers, _c1, _a1 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000122")
    _case2_id, _e2, _c2, _a2 = await _loan_case_in_credit_evaluation(client, mock_db, owner_headers, master_data, mobile_suffix="00000123")

    r = await client.get("/api/v1/loan-cases/counts", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["credit_evaluation"] == 1  # only their own assigned case
