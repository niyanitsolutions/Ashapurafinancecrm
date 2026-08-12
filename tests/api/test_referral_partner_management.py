"""End-to-end tests for Module 7 (Referral Partner Portal): Owner-creates ->
invite-and-set-password -> Owner-approval-gate lifecycle, Add Lead / View Submitted
Leads with the external (never-internal) status mapping and the "editable until
processing starts" edit cutoff (docs/decisions/DECISIONS.md), Commission Rules (Owner,
percentage/flat, product+partner scoping), and the Commission Ledger — including the
"snapshot, never recompute" guarantee: editing a CommissionRule after an entry exists
must never change that entry's stored amount.
"""

from bson import ObjectId

from app.features.auth.models import ACCOUNT_STATUS_ACTIVE
from app.features.customer.models import Application
from app.features.system_settings.models import LeadSource, LoanProduct
from app.features.workflow_engine.constants import CaseType, LoanStatus
from app.features.workflow_engine.models import ApplicationWorkflow, LoanCaseDetails
from app.security.password import hash_password
from app.worker.tasks.referral_partner import check_commission_triggers


async def _seed_referral_source_and_loan_product(mock_db) -> dict:
    source = LeadSource(name="Referral")
    source_id = (await mock_db["lead_sources"].insert_one(source.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    product = LoanProduct(name="Personal Loan")
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"source_id": str(source_id), "product_category": "loan", "product_id": str(product_id)}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1", "first_name": "Staff", "last_name": "Member", "email": email,
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


async def _create_and_approve_partner(client, mock_db, owner_headers, *, mobile="9700000001", password="PartnerPass1") -> tuple[dict, dict]:
    """Owner creates a Referral Partner (invite path — a real `users` row is created
    pending_password). Tests don't re-exercise Auth's own OTP mechanism (already covered
    by test_auth.py) — the invited user's password is set directly in mock_db, the same
    shortcut `_seed_staff_user` (conftest.py) already takes for Owner/Employee. Returns
    (partner_response, partner_headers), already Owner-approved."""
    r = await client.post(
        "/api/v1/referral-partners", json={"full_name": "Referral Co", "mobile": mobile, "business_name": "Referral Co Pvt Ltd"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    partner = r.json()["data"]
    assert partner["approval_status"] == "pending_approval"
    assert partner["partner_code"].startswith("AFS-REF-")

    await mock_db["users"].update_one({"mobile": mobile}, {"$set": {"password_hash": hash_password(password), "status": ACCOUNT_STATUS_ACTIVE}})

    r = await client.post(f"/api/v1/referral-partners/{partner['id']}/approve", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approval_status"] == "active"

    partner_headers = await _login(client, mobile, password)
    return partner, partner_headers


# ---------------------------------------------------------------------- approval lifecycle


async def test_partner_approval_lifecycle_and_pre_approval_restrictions(client, mock_db, owner_headers, employee_headers):
    r = await client.post("/api/v1/referral-partners", json={"full_name": "New Partner", "mobile": "9700000002"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    partner = r.json()["data"]

    await mock_db["users"].update_one(
        {"mobile": "9700000002"}, {"$set": {"password_hash": hash_password("PartnerPass1"), "status": ACCOUNT_STATUS_ACTIVE}}
    )
    partner_headers = await _login(client, "9700000002", "PartnerPass1")

    # Login works before approval; portal actions don't.
    r = await client.get("/api/v1/referral-partners/me", headers=partner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approval_status"] == "pending_approval"

    r = await client.post(
        "/api/v1/referral-partners/me/leads",
        json={"full_name": "Some Lead", "mobile": "9800000001", "product_category": "loan", "product_id": "000000000000000000000001"},
        headers=partner_headers,
    )
    assert r.status_code == 403, r.text

    # Only the Owner can create/approve/deactivate Referral Partners.
    r = await client.post("/api/v1/referral-partners", json={"full_name": "X", "mobile": "9700000099"}, headers=employee_headers)
    assert r.status_code == 403, r.text
    r = await client.post(f"/api/v1/referral-partners/{partner['id']}/approve", json={}, headers=employee_headers)
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/referral-partners/{partner['id']}/approve", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/referral-partners/{partner['id']}/approve", json={}, headers=owner_headers)
    assert r.status_code == 422, r.text  # already active

    r = await client.post(f"/api/v1/referral-partners/{partner['id']}/deactivate", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["approval_status"] == "deactivated"

    r = await client.post(
        "/api/v1/referral-partners/me/leads",
        json={"full_name": "Some Lead", "mobile": "9800000001", "product_category": "loan", "product_id": "000000000000000000000001"},
        headers=partner_headers,
    )
    assert r.status_code == 403, r.text  # deactivated — same as never-approved


# ---------------------------------------------------------------------- add lead / view / edit cutoff


async def test_add_lead_view_and_edit_until_processing_starts(client, mock_db, owner_headers, master_data):
    refs = await _seed_referral_source_and_loan_product(mock_db)
    _partner, partner_headers = await _create_and_approve_partner(client, mock_db, owner_headers)

    r = await client.post(
        "/api/v1/referral-partners/me/leads",
        json={"full_name": "Prospect One", "mobile": "9800000001", "product_category": refs["product_category"], "product_id": refs["product_id"], "remarks": "hot lead"},
        headers=partner_headers,
    )
    assert r.status_code == 200, r.text
    added = r.json()["data"]
    assert added["external_status"] == "submitted"
    assert added["editable"] is True
    lead_id = added["lead_id"]

    lead_doc = await mock_db["leads"].find_one({"_id": ObjectId(lead_id)})
    assert lead_doc["source_id"] == refs["source_id"]

    r = await client.get("/api/v1/referral-partners/me/leads", headers=partner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["pagination"]["total"] == 1
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["lead_id"] == lead_id

    r = await client.patch(f"/api/v1/referral-partners/me/leads/{lead_id}", json={"full_name": "Prospect One Updated"}, headers=partner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["full_name"] == "Prospect One Updated"

    employee = await _create_employee(client, owner_headers, master_data, mobile="9611111111", email="ref.officer@example.com")
    r = await client.post(f"/api/v1/leads/{lead_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/referral-partners/me/leads", headers=partner_headers)
    assert r.status_code == 200, r.text
    item = r.json()["data"][0]
    assert item["external_status"] == "in_progress"
    assert item["editable"] is False

    r = await client.patch(f"/api/v1/referral-partners/me/leads/{lead_id}", json={"full_name": "Should Fail"}, headers=partner_headers)
    assert r.status_code == 403, r.text

    r = await client.get("/api/v1/referral-partners/me/dashboard", headers=partner_headers)
    assert r.status_code == 200, r.text
    dashboard = r.json()["data"]
    assert dashboard["total_leads"] == 1
    assert dashboard["approved_leads"] == 0
    assert dashboard["rejected_leads"] == 0
    assert len(dashboard["recent_leads"]) == 1


# ---------------------------------------------------------------------- external status: approved / rejected


async def test_external_status_approved_and_rejected_never_expose_internal_status(client, mock_db, owner_headers):
    refs = await _seed_referral_source_and_loan_product(mock_db)
    _partner, partner_headers = await _create_and_approve_partner(client, mock_db, owner_headers, mobile="9700000003")

    async def _add_and_wire_case(mobile: str, current_status: str) -> str:
        r = await client.post(
            "/api/v1/referral-partners/me/leads",
            json={"full_name": "Prospect", "mobile": mobile, "product_category": refs["product_category"], "product_id": refs["product_id"]},
            headers=partner_headers,
        )
        assert r.status_code == 200, r.text
        lead_id = r.json()["data"]["lead_id"]

        application = Application(
            application_code="AFS-APP-TEST", user_id="000000000000000000000001", lead_id=lead_id,
            product_category=refs["product_category"], product_id=refs["product_id"], form_definition_id="000000000000000000000002",
        )
        app_result = await mock_db["applications"].insert_one(application.model_dump(by_alias=True, exclude={"id"}))

        case = ApplicationWorkflow(
            case_code=f"AFS-LOAN-{mobile}", case_type=CaseType.LOAN, application_id=str(app_result.inserted_id), customer_id="000000000000000000000003",
            product_id=refs["product_id"], product_category=refs["product_category"], current_status=current_status,
            loan_details=LoanCaseDetails(disbursed_amount=100000.0) if current_status == LoanStatus.DISBURSED else None,
        )
        await mock_db["application_workflows"].insert_one(case.model_dump(by_alias=True, exclude={"id"}))
        return lead_id

    await _add_and_wire_case("9800000002", LoanStatus.DISBURSED)
    await _add_and_wire_case("9800000003", LoanStatus.REJECTED)

    r = await client.get("/api/v1/referral-partners/me/leads", headers=partner_headers)
    assert r.status_code == 200, r.text
    by_mobile = {item["mobile"]: item for item in r.json()["data"]}
    assert by_mobile["9800000002"]["external_status"] == "approved"
    assert by_mobile["9800000002"]["editable"] is False
    assert by_mobile["9800000003"]["external_status"] == "rejected"
    assert by_mobile["9800000003"]["editable"] is False
    for item in r.json()["data"]:
        assert item["external_status"] not in ("disbursed", "credit_evaluation", "documents_pending", "new_customer")

    r = await client.get("/api/v1/referral-partners/me/dashboard", headers=partner_headers)
    dashboard = r.json()["data"]
    assert dashboard["total_leads"] == 2
    assert dashboard["approved_leads"] == 1
    assert dashboard["rejected_leads"] == 1


# ---------------------------------------------------------------------- commission rules + ledger + snapshot


async def test_commission_rule_crud_entry_creation_and_snapshot_is_immutable(client, mock_db, owner_headers, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.referral_partner.get_database", lambda: mock_db)
    refs = await _seed_referral_source_and_loan_product(mock_db)
    partner, partner_headers = await _create_and_approve_partner(client, mock_db, owner_headers, mobile="9700000004")

    r = await client.post(
        "/api/v1/commission-rules",
        json={"label": "Personal Loan default", "product_category": "loan", "calculation_type": "percentage", "rate_or_amount": 2.0, "trigger_event": "loan_disbursed"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    rule = r.json()["data"]
    assert rule["status"] == "active"

    r = await client.get("/api/v1/commission-rules", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 1

    r = await client.post(
        "/api/v1/referral-partners/me/leads",
        json={"full_name": "Big Ticket", "mobile": "9800000004", "product_category": "loan", "product_id": refs["product_id"]},
        headers=partner_headers,
    )
    assert r.status_code == 200, r.text
    lead_id = r.json()["data"]["lead_id"]

    application = Application(
        application_code="AFS-APP-COMM", user_id="000000000000000000000001", lead_id=lead_id,
        product_category="loan", product_id=refs["product_id"], form_definition_id="000000000000000000000002",
    )
    app_result = await mock_db["applications"].insert_one(application.model_dump(by_alias=True, exclude={"id"}))
    case = ApplicationWorkflow(
        case_code="AFS-LOAN-COMM", case_type=CaseType.LOAN, application_id=str(app_result.inserted_id), customer_id="000000000000000000000003",
        product_id=refs["product_id"], product_category="loan", current_status=LoanStatus.DISBURSED,
        loan_details=LoanCaseDetails(disbursed_amount=100000.0),
    )
    await mock_db["application_workflows"].insert_one(case.model_dump(by_alias=True, exclude={"id"}))

    await check_commission_triggers({})
    r = await client.get("/api/v1/commission-entries", headers=owner_headers)
    assert r.status_code == 200, r.text
    entries = r.json()["data"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["base_amount"] == 100000.0
    assert entry["commission_amount"] == 2000.0
    assert entry["status"] == "pending"
    assert entry["partner_name"] == "Referral Co"
    entry_id = entry["id"]

    await check_commission_triggers({})  # idempotent
    r = await client.get("/api/v1/commission-entries", headers=owner_headers)
    assert len(r.json()["data"]) == 1

    # Snapshot guarantee: editing the rule's rate afterward must never change the entry.
    r = await client.patch(f"/api/v1/commission-rules/{rule['id']}", json={"rate_or_amount": 5.0}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/commission-entries", headers=owner_headers)
    assert r.json()["data"][0]["commission_amount"] == 2000.0  # unchanged, not recomputed at 5%

    r = await client.post(f"/api/v1/commission-entries/{entry_id}/settle", json={"payment_reference": "REF1"}, headers=owner_headers)
    assert r.status_code == 422, r.text  # pending, not approved yet

    r = await client.post(f"/api/v1/commission-entries/{entry_id}/approve", json={}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "approved"

    r = await client.post(f"/api/v1/commission-entries/{entry_id}/settle", json={"payment_reference": "REF1"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "paid"
    assert r.json()["data"]["payment_reference"] == "REF1"

    r = await client.get("/api/v1/referral-partners/me/commission-entries", headers=partner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"][0]["status"] == "paid"

    r = await client.get("/api/v1/referral-partners/me/dashboard", headers=partner_headers)
    dashboard = r.json()["data"]
    assert dashboard["commission_paid"] == 2000.0
    assert dashboard["commission_pending"] == 0.0
    assert dashboard["commission_balance"] == 0.0
