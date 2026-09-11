"""Remaining Insurance Management production changes:
 - Policy Lead assignment -> ACTIVE Advisors only (inactive / non-advisor rejected server-side)
 - Insurance hold-reason vocabulary + "Other" free-text, persisted with the hold info
 - "On Hold" as a real Policy Leads tab: hold from any stage, previous stage preserved, resume returns
 - Policy Leads tab count badges (server-computed, per InsuranceStatus)
 - "+ Add Insurance Lead" extended applicant fields persisted in Application.form_data
 - Other Documents: staff upload / re-upload with history, never a Product Schema change,
   the required-schema-document gate unchanged

Insurance-only; Loan is never exercised here.
"""

from datetime import date, datetime

from bson import ObjectId
from test_case_status_control import _create_employee, _grant_case_permission, _login
from test_insurance_policy_leads import _case_for, _insurance_product_with_schema
from test_workflow import _seed_workflow_definitions, _submitted_application

from app.features.customer.models import ApplicationDocument
from app.features.recruitment.models import Advisor
from app.utils.datetime import ist_date_to_utc_midnight

_MANUAL = "/api/v1/insurance-cases/manual"


async def _verified_schema_doc(mock_db, application_id: str, document_type_id: str) -> None:
    """A manual lead has no uploaded documents — insert a VERIFIED one directly so the
    Policy Document -> Policy Login gate can be exercised."""
    doc = ApplicationDocument(
        application_id=application_id, document_type_id=document_type_id, file_name="pan.pdf", s3_key="k/pan.pdf",
        verification_status="verified", document_status="uploaded", is_current=True,
    )
    await mock_db["application_documents"].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))


async def _advisor(mock_db, *, name="Ravi Kumar", channel="qr", status="active", mobile="9800000001") -> str:
    doc = Advisor(
        advisor_code=f"AFS-ADV-{mobile[-6:]}", recruitment_lead_id=str(ObjectId()), full_name=name,
        mobile=mobile, channel=channel, status=status,
    ).model_dump(by_alias=True, exclude={"id"})
    return str((await mock_db["advisors"].insert_one(doc)).inserted_id)


async def _product(mock_db):
    await _seed_workflow_definitions(mock_db)
    return await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])


async def _manual_case(client, headers, product, **extra):
    body = {
        "full_name": "Lead Person", "mobile": extra.pop("mobile", "9876500055"), "age": 34,
        "insurance_category_id": product["category_id"], "product_id": product["product_id"],
        "stage": extra.pop("stage", "fresh_lead"), **extra,
    }
    r = await client.post(_MANUAL, json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------------------------------------------------------------- assignment -> active advisors


async def test_assign_active_advisor_qr_and_non_qr(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    qr = await _advisor(mock_db, name="Ravi QR", channel="qr", mobile="9800000010")
    non_qr = await _advisor(mock_db, name="Kumar NonQR", channel="non_qr", mobile="9800000011")

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": qr}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to_name"] == "Ravi QR"

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": non_qr}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to_name"] == "Kumar NonQR"


async def test_assign_inactive_advisor_rejected(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    inactive = await _advisor(mock_db, name="Suresh Inactive", status="inactive", mobile="9800000012")

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": inactive}, headers=owner_headers)
    assert r.status_code == 422, r.text
    assert "inactive" in r.json()["error"]["message"].lower()
    # Case stays unassigned.
    assert (await client.get(f"/api/v1/insurance-cases/{case['id']}", headers=owner_headers)).json()["data"]["assigned_to"] is None


async def test_assign_non_advisor_id_rejected(client, mock_db, owner_headers, master_data):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    # An employee id is not an advisor id.
    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": "9500000099", "initial_password": "InitialPass1!", "first_name": "Not", "last_name": "Advisor",
            "email": "notadvisor@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-15", "employment_type": "full_time",
        },
        headers=owner_headers,
    )
    employee_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": employee_id}, headers=owner_headers)
    assert r.status_code == 422, r.text
    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": str(ObjectId())}, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_assign_requires_the_existing_assign_permission(client, mock_db, owner_headers, master_data):
    """The advisor-lookup fix must not loosen who is allowed to assign — an Employee
    without the `assign` action on insurance_management:applications is still 403'd,
    exactly like before this change (the Owner can always assign)."""
    product = await _product(mock_db)
    advisor_id = await _advisor(mock_db, mobile="9800000040")

    # Grant the full action set first (this is what creates the permission catalog entry
    # for insurance_management:applications in this test's mock_db); a second grant to a
    # different employee then reuses that same catalog entry with a narrower action set.
    can_assign = await _create_employee(client, owner_headers, master_data, mobile="9500000302", email="canassign@example.com")
    await _grant_case_permission(client, owner_headers, can_assign["id"], module="insurance_management", actions=["view", "edit", "assign"])
    can_assign_headers = await _login(client, "9500000302", "InitialPass1!")
    # This employee created the case themselves, so they also have visibility into it —
    # isolates the assertion to the `assign` action grant, not the separate (unchanged,
    # out of scope) created-by visibility rule.
    own_case = await _manual_case(client, can_assign_headers, product, mobile="9876500801")

    no_assign = await _create_employee(client, owner_headers, master_data, mobile="9500000301", email="noassign@example.com")
    await _grant_case_permission(client, owner_headers, no_assign["id"], module="insurance_management", actions=["view", "edit"])
    no_assign_headers = await _login(client, "9500000301", "InitialPass1!")
    r = await client.post(f"/api/v1/insurance-cases/{own_case['id']}/assign", json={"advisor_id": advisor_id}, headers=no_assign_headers)
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/insurance-cases/{own_case['id']}/assign", json={"advisor_id": advisor_id}, headers=can_assign_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to"] == advisor_id


async def test_assign_and_reassign_are_audit_logged(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    advisor_a = await _advisor(mock_db, name="Advisor A", mobile="9800000041")
    advisor_b = await _advisor(mock_db, name="Advisor B", mobile="9800000042")

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": advisor_a}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": advisor_b}, headers=owner_headers)
    assert r.status_code == 200, r.text

    events = await mock_db["audit_logs"].find({"metadata.application_workflow_id": case["id"]}).to_list(length=50)
    event_types = {e["event_type"] for e in events}
    assert "workflow_case_assigned" in event_types
    assert "workflow_case_reassigned" in event_types
    reassigned = next(e for e in events if e["event_type"] == "workflow_case_reassigned")
    assert reassigned["metadata"]["advisor_id"] == advisor_b


async def test_assigned_advisor_name_and_channel_shown_on_case_overview(client, mock_db, owner_headers):
    """Case detail carries both the advisor's name and raw Type (`channel`) so the
    frontend can render "Name — QR"/"Name — Non QR" without a second lookup."""
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    advisor_id = await _advisor(mock_db, name="testing001", channel="qr", mobile="9800000043")

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/assign", json={"advisor_id": advisor_id}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assigned_to_name"] == "testing001"
    assert r.json()["data"]["assigned_to_channel"] == "qr"

    detail = (await client.get(f"/api/v1/insurance-cases/{case['id']}", headers=owner_headers)).json()["data"]
    assert detail["assigned_to_name"] == "testing001"
    assert detail["assigned_to_channel"] == "qr"


# ---------------------------------------------------------------- hold reasons


async def test_all_insurance_hold_reasons_accepted(client, mock_db, owner_headers):
    product = await _product(mock_db)
    for i, reason in enumerate(
        ["underwriting_issues", "medical_pending", "document_not_clear", "payment_pending", "document_pending"]
    ):
        case = await _manual_case(client, owner_headers, product, mobile=f"987650010{i}")
        r = await client.post(f"/api/v1/insurance-cases/{case['id']}/hold", json={"reason": reason}, headers=owner_headers)
        assert r.status_code == 200, (reason, r.text)
        data = r.json()["data"]
        assert data["current_status"] == "on_hold"
        assert data["on_hold_reason"] == reason
        assert data["on_hold_other_reason"] is None


async def test_hold_other_requires_and_persists_free_text(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)

    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/hold", json={"reason": "other"}, headers=owner_headers)
    assert r.status_code == 422, r.text  # Other with no free text

    r = await client.post(
        f"/api/v1/insurance-cases/{case['id']}/hold",
        json={"reason": "other", "other_reason": "Customer requested callback tomorrow"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["on_hold_reason"] == "other"
    assert data["on_hold_other_reason"] == "Customer requested callback tomorrow"

    # Persisted, not just in the response.
    wf = await mock_db["application_workflows"].find_one({"_id": ObjectId(case["id"])})
    assert wf["on_hold_other_reason"] == "Customer requested callback tomorrow"


async def test_unknown_hold_reason_rejected(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product)
    r = await client.post(
        f"/api/v1/insurance-cases/{case['id']}/hold", json={"reason": "waiting_for_bank"}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- On Hold: previous stage preserved


async def test_hold_from_each_stage_preserves_previous_and_resume_returns(client, mock_db, owner_headers):
    product = await _product(mock_db)
    # fresh_lead
    fresh = await _manual_case(client, owner_headers, product, mobile="9876500201")
    # policy_document
    doc_case = await _manual_case(client, owner_headers, product, mobile="9876500202", stage="policy_document")
    # policy_login needs the schema doc verified, then a move.
    login_case = await _manual_case(client, owner_headers, product, mobile="9876500203", stage="policy_document")
    await _verified_schema_doc(mock_db, login_case["application_id"], product["document_type_id"])
    r = await client.post(f"/api/v1/insurance-cases/{login_case['id']}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text

    for case_id, previous in (
        (fresh["id"], "fresh_lead"), (doc_case["id"], "policy_document"), (login_case["id"], "policy_login"),
    ):
        r = await client.post(f"/api/v1/insurance-cases/{case_id}/hold", json={"reason": "medical_pending"}, headers=owner_headers)
        assert r.status_code == 200, (previous, r.text)
        assert r.json()["data"]["current_status"] == "on_hold"
        wf = await mock_db["application_workflows"].find_one({"_id": ObjectId(case_id)})
        assert wf["on_hold_previous_status"] == previous

        r = await client.post(f"/api/v1/insurance-cases/{case_id}/resume", headers=owner_headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["current_status"] == previous
        wf = await mock_db["application_workflows"].find_one({"_id": ObjectId(case_id)})
        assert wf["on_hold_reason"] is None and wf["on_hold_other_reason"] is None


# ---------------------------------------------------------------- counts


async def test_counts_reflect_status_distribution(client, mock_db, owner_headers):
    product = await _product(mock_db)
    a = await _manual_case(client, owner_headers, product, mobile="9876500301")  # fresh_lead
    await _manual_case(client, owner_headers, product, mobile="9876500302", stage="policy_document")
    await _manual_case(client, owner_headers, product, mobile="9876500303", stage="policy_document")
    await client.post(f"/api/v1/insurance-cases/{a['id']}/hold", json={"reason": "payment_pending"}, headers=owner_headers)

    counts = (await client.get("/api/v1/insurance-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["fresh_lead"] == 0
    assert counts["policy_document"] == 2
    assert counts["on_hold"] == 1
    assert set(counts) == {
        "fresh_lead", "policy_document", "policy_login", "payment", "policy_issued", "re_eligible", "on_hold", "rejected",
    }

    # Moving one case updates the counts.
    b = await _manual_case(client, owner_headers, product, mobile="9876500304")  # fresh_lead
    await client.patch(f"/api/v1/insurance-cases/{b['id']}/status", json={"status": "policy_document"}, headers=owner_headers)
    counts = (await client.get("/api/v1/insurance-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["policy_document"] == 3


# ---------------------------------------------------------------- manual lead extended fields


async def test_manual_lead_extended_fields_persist_and_return(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(
        client, owner_headers, product,
        alternate_mobile="9123456780", height=172, weight=72, mother_name="Lakshmi", father_name="Ramesh",
        education="B.Tech", company_name="ABC Pvt Ltd", designation="Manager",
        nominee_name="Priya Kumar", nominee_dob="1995-05-15", nominee_relationship="Wife",
    )
    detail = (await client.get(f"/api/v1/insurance-cases/{case['id']}", headers=owner_headers)).json()["data"]
    a = detail["applicant"]
    assert a["alternate_mobile"] == "9123456780"
    assert a["height"] == 172 and a["weight"] == 72
    assert a["mother_name"] == "Lakshmi" and a["father_name"] == "Ramesh"
    assert a["education"] == "B.Tech"
    assert a["company_name"] == "ABC Pvt Ltd" and a["designation"] == "Manager"
    assert a["nominee_name"] == "Priya Kumar" and a["nominee_dob"] == "1995-05-15" and a["nominee_relationship"] == "Wife"

    application = await mock_db["applications"].find_one({"_id": ObjectId(case["application_id"])})
    assert application["form_data"]["nominee_dob"] == "1995-05-15"


async def test_manual_lead_alternate_mobile_optional_but_validated(client, mock_db, owner_headers):
    product = await _product(mock_db)
    # Omitted -> fine.
    ok = await _manual_case(client, owner_headers, product, mobile="9876500401")
    assert (await client.get(f"/api/v1/insurance-cases/{ok['id']}", headers=owner_headers)).json()["data"]["applicant"]["alternate_mobile"] is None
    # Present but invalid -> 422.
    body = {
        "full_name": "X", "mobile": "9876500402", "age": 30, "alternate_mobile": "12345",
        "insurance_category_id": product["category_id"], "product_id": product["product_id"], "stage": "fresh_lead",
    }
    assert (await client.post(_MANUAL, json=body, headers=owner_headers)).status_code == 422


async def test_old_case_without_extended_fields_still_loads(client, mock_db, owner_headers):
    """A case from a portal submission (no extended fields) returns an all-null applicant."""
    product = await _insurance_product_with_schema(mock_db, product_name="Portal Plan", docs=["PAN"])
    await _seed_workflow_definitions(mock_db)
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9641110001")
    case_id = await _case_for(client, owner_headers, application_id)
    a = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]["applicant"]
    assert a["height"] is None and a["nominee_name"] is None and a["mother_name"] is None


# ---------------------------------------------------------------- Other Documents: upload / re-upload / history


async def _other_doc_case(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case = await _manual_case(client, owner_headers, product, stage="policy_document")
    return case["id"]


async def test_other_document_staff_upload_verify_reject_reupload_history(client, mock_db, owner_headers):
    case_id = await _other_doc_case(client, mock_db, owner_headers)

    # Add (name only) -> pending upload.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/other-documents", json={"name": "Medical Prescription"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    doc_id = r.json()["data"]["id"]
    assert r.json()["data"]["document_status"] == "requested"

    # Staff upload.
    up = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/upload-url",
        json={"file_name": "prescription.pdf"}, headers=owner_headers,
    )
    assert up.status_code == 200, up.text
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/confirm",
        json={"file_name": "prescription.pdf"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "uploaded"
    assert r.json()["data"]["file_name"] == "prescription.pdf"
    assert r.json()["data"]["download_url"]

    # Reject.
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/reject",
        json={"reason": "Document not clear"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "rejected"

    # Re-upload -> a NEW current version, old one kept in history.
    await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/upload-url",
        json={"file_name": "prescription_new.pdf"}, headers=owner_headers,
    )
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/confirm",
        json={"file_name": "prescription_new.pdf"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    new_id = r.json()["data"]["id"]
    assert new_id != doc_id
    assert r.json()["data"]["doc_version"] == 2
    assert r.json()["data"]["verification_status"] == "pending"

    # The list shows only the current version.
    listed = (await client.get(f"/api/v1/insurance-cases/{case_id}/other-documents", headers=owner_headers)).json()["data"]
    prescriptions = [d for d in listed if d["name"] == "Medical Prescription"]
    assert len(prescriptions) == 1 and prescriptions[0]["id"] == new_id

    # History returns both versions; the old one is not deleted.
    history = (await client.get(f"/api/v1/insurance-cases/{case_id}/other-documents/{new_id}/history", headers=owner_headers)).json()["data"]
    assert {h["file_name"] for h in history} == {"prescription.pdf", "prescription_new.pdf"}
    old = await mock_db["insurance_case_additional_documents"].find_one({"_id": ObjectId(doc_id)})
    assert old is not None and old["is_current"] is False


async def test_verify_other_document(client, mock_db, owner_headers):
    case_id = await _other_doc_case(client, mock_db, owner_headers)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/other-documents", json={"name": "Address Proof"}, headers=owner_headers)
    doc_id = r.json()["data"]["id"]
    await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/upload-url", json={"file_name": "a.pdf"}, headers=owner_headers
    )
    await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/confirm", json={"file_name": "a.pdf"}, headers=owner_headers
    )
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/other-documents/{doc_id}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"


# ---------------------------------------------------------------- Other Documents never touch the Product Schema


async def test_other_document_does_not_modify_product_schema_or_block_the_gate(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Schema Plan", docs=["PAN"])
    case_a = await _manual_case(client, owner_headers, product, mobile="9876500601", stage="policy_document")
    case_b = await _manual_case(client, owner_headers, product, mobile="9876500602", stage="policy_document")

    form_def_before = await mock_db["application_form_definitions"].find_one({"product_id": product["product_id"]})
    r = await client.post(
        f"/api/v1/insurance-cases/{case_a['id']}/other-documents", json={"name": "Medical Note"}, headers=owner_headers
    )
    med_id = r.json()["data"]["id"]
    await client.post(
        f"/api/v1/insurance-cases/{case_a['id']}/other-documents/{med_id}/upload-url", json={"file_name": "m.pdf"}, headers=owner_headers
    )
    await client.post(
        f"/api/v1/insurance-cases/{case_a['id']}/other-documents/{med_id}/confirm", json={"file_name": "m.pdf"}, headers=owner_headers
    )

    # The Product Schema is byte-for-byte unchanged, so case B is unaffected.
    form_def_after = await mock_db["application_form_definitions"].find_one({"product_id": product["product_id"]})
    assert form_def_after["required_documents"] == form_def_before["required_documents"]
    b_detail = (await client.get(f"/api/v1/insurance-cases/{case_b['id']}", headers=owner_headers)).json()["data"]
    assert b_detail["required_documents"]["required_total"] == 1  # just PAN, no "Medical Note"

    # Gate still enforced on case A: schema PAN unverified + Medical Note only "pending" -> blocked.
    r = await client.post(f"/api/v1/insurance-cases/{case_a['id']}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 409, r.text

    # Verifying the schema PAN alone lets it through — the unverified Other Document never blocked it.
    await _verified_schema_doc(mock_db, case_a["application_id"], product["document_type_id"])
    r = await client.post(f"/api/v1/insurance-cases/{case_a['id']}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- Policy Login: Issue Date


async def _to_policy_login(client, headers, mock_db, product, *, mobile):
    case = await _manual_case(client, headers, product, mobile=mobile, stage="policy_document")
    await _verified_schema_doc(mock_db, case["application_id"], product["document_type_id"])
    r = await client.post(f"/api/v1/insurance-cases/{case['id']}/move-to-policy-login", headers=headers)
    assert r.status_code == 200, r.text
    return case["id"]


def _expected_issue_date_iso(calendar_date: str) -> datetime:
    """The exact stored/returned instant for a `policy_issue_date` calendar date — IST
    midnight of that date, expressed in UTC (same conversion the service applies)."""
    return ist_date_to_utc_midnight(date.fromisoformat(calendar_date))


async def test_policy_login_saves_and_returns_issue_date(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500701")

    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 20000, "ppt": 10, "pt": 10, "policy_number": "POL123456789", "policy_issue_date": "2026-09-10"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    saved = datetime.fromisoformat(r.json()["data"]["insurance_details"]["policy_issue_date"])
    assert saved == _expected_issue_date_iso("2026-09-10")

    # Reopening (re-fetching) the case returns the exact same saved instant.
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert datetime.fromisoformat(detail["insurance_details"]["policy_issue_date"]) == _expected_issue_date_iso("2026-09-10")
    assert detail["insurance_details"]["policy_number"] == "POL123456789"


async def test_policy_login_issue_date_is_editable(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500702")

    await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login", json={"policy_issue_date": "2026-09-10"}, headers=owner_headers
    )
    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login", json={"policy_issue_date": "2026-10-01"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    saved = datetime.fromisoformat(r.json()["data"]["insurance_details"]["policy_issue_date"])
    assert saved == _expected_issue_date_iso("2026-10-01")


async def test_policy_login_without_issue_date_still_works(client, mock_db, owner_headers):
    """Existing Policy Login behaviour (Premium/PPT/PT/Policy Number/Remarks, no Issue
    Date) is completely unaffected — the new field is additive and optional."""
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500703")

    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 15000, "ppt": 5, "pt": 15, "policy_number": "POL999", "remarks": "ok"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]["insurance_details"]
    assert data["policy_issue_date"] is None
    assert data["premium_amount"] == 15000 and data["policy_number"] == "POL999"


async def test_old_case_without_issue_date_field_still_loads(client, mock_db, owner_headers):
    """A pre-existing `insurance_details` document (written before `policy_issue_date`
    existed) must still validate and load, showing null rather than erroring."""
    product = await _insurance_product_with_schema(mock_db, product_name="Legacy Plan", docs=["PAN"])
    await _seed_workflow_definitions(mock_db)
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9641110002")
    case_id = await _case_for(client, owner_headers, application_id)
    # Simulate a document written before this field existed.
    await mock_db["application_workflows"].update_one(
        {"_id": ObjectId(case_id)},
        {"$set": {"insurance_details.premium_amount": 5000}, "$unset": {"insurance_details.policy_issue_date": ""}},
    )
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["insurance_details"]["policy_issue_date"] is None
    assert detail["insurance_details"]["premium_amount"] == 5000


async def test_invalid_issue_date_rejected(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500704")

    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login", json={"policy_issue_date": "2026-99-99"}, headers=owner_headers
    )
    assert r.status_code == 422, r.text
    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login", json={"policy_issue_date": "not-a-date"}, headers=owner_headers
    )
    assert r.status_code == 422, r.text
    # Rejected — nothing was silently written.
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["insurance_details"]["policy_issue_date"] is None


async def test_issue_date_does_not_weaken_policy_login_gates(client, mock_db, owner_headers):
    """Adding Issue Date must not bypass the existing Premium/PPT/PT-required gate for
    Move to Payment, nor the Payment stage's own fully-paid gate for Move to Policy
    Issued (production add-on: Payment now sits between the two)."""
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500705")

    # Issue Date alone (no premium/ppt/pt) does NOT satisfy the Move-to-Payment gate.
    await client.patch(f"/api/v1/insurance-cases/{case_id}/policy-login", json={"policy_issue_date": "2026-09-10"}, headers=owner_headers)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-payment", headers=owner_headers)
    assert r.status_code == 422, r.text

    # Once premium/ppt/pt are also recorded, the existing gate opens exactly as before.
    await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 20000, "ppt": 10, "pt": 10}, headers=owner_headers,
    )
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-payment", headers=owner_headers)
    assert r.status_code == 200, r.text

    # At Payment, Issue Date being set does NOT itself unlock Move to Policy Issued —
    # the case is still Not Paid.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 422, r.text

    # Fully paying opens the gate exactly as expected.
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20000}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_policy_issued_retains_and_returns_issue_date(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500706")
    await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 20000, "ppt": 10, "pt": 10, "policy_number": "POL42", "policy_issue_date": "2026-09-10"},
        headers=owner_headers,
    )
    assert (await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-payment", headers=owner_headers)).status_code == 200
    assert (
        await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20000}, headers=owner_headers)
    ).status_code == 200

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]["insurance_details"]
    assert datetime.fromisoformat(data["policy_issue_date"]) == _expected_issue_date_iso("2026-09-10")
    assert data["policy_number"] == "POL42"

    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert datetime.fromisoformat(detail["insurance_details"]["policy_issue_date"]) == _expected_issue_date_iso("2026-09-10")
    assert detail["current_status"] == "policy_issued"


# ---------------------------------------------------------------- Payment stage (production add-on)


async def _to_payment(client, headers, mock_db, product, *, mobile, premium=20000, ppt=10, pt=10, issue_date=None):
    case_id = await _to_policy_login(client, headers, mock_db, product, mobile=mobile)
    body = {"premium_amount": premium, "ppt": ppt, "pt": pt}
    if issue_date:
        body["policy_issue_date"] = issue_date
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/policy-login", json=body, headers=headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-payment", headers=headers)
    assert r.status_code == 200, r.text
    return case_id


async def test_policy_login_to_payment_works_and_starts_not_paid(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500801")

    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["current_status"] == "payment"
    assert detail["insurance_details"]["payment_status"] == "not_paid"
    assert detail["insurance_details"]["amount_paid"] == 0


async def test_payment_is_a_real_stage_with_correct_tab_count(client, mock_db, owner_headers):
    product = await _product(mock_db)
    await _to_payment(client, owner_headers, mock_db, product, mobile="9876500802")
    await _to_payment(client, owner_headers, mock_db, product, mobile="9876500803")

    counts = (await client.get("/api/v1/insurance-cases/counts", headers=owner_headers)).json()["data"]
    assert counts["payment"] == 2

    r = await client.get("/api/v1/insurance-cases?status=payment&page_size=100", headers=owner_headers)
    body = r.json()
    assert body["meta"]["pagination"]["total"] == 2
    assert all(row["current_status"] == "payment" for row in body["data"])


async def test_not_paid_cannot_move_to_policy_issued(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500804")
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 422, r.text
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["current_status"] == "payment"


async def test_partially_paid_cannot_move_to_policy_issued(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500805", premium=20000)
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 10000}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["insurance_details"]["payment_status"] == "partially_paid"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_fully_paid_with_issue_date_can_move_to_policy_issued(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500806", premium=20000, issue_date="2026-09-11")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20000}, headers=owner_headers)
    assert r.json()["data"]["insurance_details"]["payment_status"] == "fully_paid"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_issued"


async def test_fully_paid_without_issue_date_cannot_move_to_policy_issued(client, mock_db, owner_headers):
    """Fully Paid alone is not enough — the Issue Date (recorded at Policy Login) must
    also be present, matching the Payment panel's own "Move to Policy Issued" gate."""
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500807", premium=20000)
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20000}, headers=owner_headers)
    assert r.json()["data"]["insurance_details"]["payment_status"] == "fully_paid"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_amount_paid_cannot_exceed_premium(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500808", premium=20000)
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20001}, headers=owner_headers)
    assert r.status_code == 422, r.text
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["insurance_details"]["amount_paid"] == 0  # unchanged — the invalid write never landed


async def test_negative_amount_paid_is_rejected(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500809")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": -1}, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_balance_is_premium_minus_amount_paid(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500810", premium=20000)
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 12500}, headers=owner_headers)
    data = r.json()["data"]["insurance_details"]
    assert data["premium_amount"] - data["amount_paid"] == 7500

    # Same numbers on the Payment tab's list row (frontend computes Balance from these).
    row = next(
        r for r in (await client.get("/api/v1/insurance-cases?status=payment&page_size=100", headers=owner_headers)).json()["data"]
        if r["id"] == case_id
    )
    assert row["premium_amount"] == 20000 and row["amount_paid"] == 12500


async def test_payment_status_can_never_be_submitted_directly(client, mock_db, owner_headers):
    """No request schema accepts `payment_status` — even if a client stuffs it into the
    body, the server-computed value (from `amount_paid`) is the only thing ever stored."""
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500811", premium=20000)
    r = await client.patch(
        f"/api/v1/insurance-cases/{case_id}/payment",
        json={"amount_paid": 10000, "payment_status": "fully_paid"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    # The extra field is silently ignored (Pydantic default) — the real, computed status
    # reflects the actual amount, not the spoofed one.
    assert r.json()["data"]["insurance_details"]["payment_status"] == "partially_paid"


async def test_direct_move_to_policy_issued_from_policy_login_is_rejected(client, mock_db, owner_headers):
    """Bypassing Payment entirely (calling the endpoint straight from Policy Login) is
    rejected — Payment is a real, backend-enforced stage, not a frontend-only filter."""
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500812")
    await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 20000, "ppt": 10, "pt": 10, "policy_issue_date": "2026-09-11"}, headers=owner_headers,
    )
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-issued", headers=owner_headers)
    assert r.status_code == 409, r.text
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["current_status"] == "policy_login"


async def test_move_case_to_stage_walks_through_payment_and_stops_if_unpaid(client, mock_db, owner_headers):
    """The generic staff "Move To" jump from Policy Login straight to Policy Issued walks
    the chain hop by hop and stops at Payment (still genuinely unpaid) rather than
    silently skipping it."""
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500813")
    await client.patch(
        f"/api/v1/insurance-cases/{case_id}/policy-login",
        json={"premium_amount": 20000, "ppt": 10, "pt": 10}, headers=owner_headers,
    )
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_issued"}, headers=owner_headers)
    assert r.status_code == 422, r.text
    detail = (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]
    assert detail["current_status"] == "payment"  # got as far as it legally could


async def test_payment_update_is_audited_and_recorded_in_history(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500814", premium=20000)
    await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 10000}, headers=owner_headers)
    await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 20000}, headers=owner_headers)

    audits = await mock_db["audit_logs"].find({"event_type": "insurance_case_payment_updated"}).to_list(length=50)
    assert len(audits) == 2
    assert audits[0]["metadata"]["to_amount"] == 10000
    assert audits[1]["metadata"]["from_amount"] == 10000 and audits[1]["metadata"]["to_amount"] == 20000

    timeline = (await client.get(f"/api/v1/insurance-cases/{case_id}/timeline", headers=owner_headers)).json()["data"]
    assert any("Payment updated" in (e.get("text") or "") for e in timeline)
    assert any("partially_paid" in (e.get("text") or "") or "fully_paid" in (e.get("text") or "") for e in timeline)


async def test_payment_can_only_be_updated_at_payment_stage(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_policy_login(client, owner_headers, mock_db, product, mobile="9876500815")
    r = await client.patch(f"/api/v1/insurance-cases/{case_id}/payment", json={"amount_paid": 100}, headers=owner_headers)
    assert r.status_code == 409, r.text


async def test_hold_and_resume_work_from_payment_stage(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500816")
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/hold", json={"reason": "payment_pending"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "on_hold"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/resume", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "payment"  # returns to the stage it was held from


async def test_reject_works_from_payment_stage(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500817")
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject", json={"reason": "Customer withdrew", "re_eligibility": "no"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "rejected"


async def test_move_back_from_payment_to_policy_login(client, mock_db, owner_headers):
    product = await _product(mock_db)
    case_id = await _to_payment(client, owner_headers, mock_db, product, mobile="9876500818")
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-back", json={"target": "policy_login"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_login"
