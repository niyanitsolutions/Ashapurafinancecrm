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

from bson import ObjectId
from test_insurance_policy_leads import _case_for, _insurance_product_with_schema
from test_workflow import _seed_workflow_definitions, _submitted_application

from app.features.customer.models import ApplicationDocument
from app.features.recruitment.models import Advisor

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
        "fresh_lead", "policy_document", "policy_login", "policy_issued", "re_eligible", "on_hold", "rejected",
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
