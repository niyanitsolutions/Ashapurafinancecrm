"""Insurance "Policy Leads" redesign — Phase 3: the new
fresh_lead → policy_document → policy_login → policy_issued pipeline, the
verified-required-documents gate, Move Back, Reject + Re-Eligibility scheduling,
product change (re-resolves the Product Schema, preserves uploaded documents),
Re-Eligible restart, and the migration remap. Loan is never exercised here.
"""

import sys
from pathlib import Path

import pytest
from bson import ObjectId

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from migrate_redesign_insurance_pipeline import _remap_cases, _rewrite_definitions
from test_workflow import (
    _seed_workflow_definitions,
    _signup_via_otp,
    _submitted_application,
    _verify_all_current_documents,
)

from app.features.customer.constants import FieldType
from app.features.customer.models import (
    ApplicationFormDefinition,
    FormFieldDefinition,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import (
    DocumentType,
    InsuranceCategory,
    InsuranceProduct,
)


async def _insurance_product_with_schema(mock_db, *, category_name="Health Insurance", product_name, docs, front_back=(), optional=()):
    cat_id = str(
        (await mock_db["insurance_categories"].find_one({"name": category_name}) or {}).get("_id")
        or (await mock_db["insurance_categories"].insert_one(InsuranceCategory(name=category_name).model_dump(by_alias=True, exclude={"id"}))).inserted_id
    )
    product_id = str(
        (await mock_db["insurance_products"].insert_one(
            InsuranceProduct(name=product_name, category_id=cat_id).model_dump(by_alias=True, exclude={"id"})
        )).inserted_id
    )
    doc_ids = []
    required_documents = []
    for name in docs:
        doc_id = str((await mock_db["document_types"].insert_one(DocumentType(name=name).model_dump(by_alias=True, exclude={"id"}))).inserted_id)
        doc_ids.append(doc_id)
        required_documents.append(
            RequiredDocumentDefinition(
                document_type_id=doc_id, required=name not in optional, front_back_upload=name in front_back
            )
        )
    form_def = ApplicationFormDefinition(
        product_category="insurance", product_id=product_id, insurance_category_id=cat_id,
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=required_documents, status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return {
        "product_category": "insurance", "product_id": product_id, "category_id": cat_id,
        "document_type_id": doc_ids[0], "document_type_ids": doc_ids,
    }


async def _case_for(client, owner_headers, application_id):
    cases = (await client.get("/api/v1/insurance-cases", headers=owner_headers)).json()["data"]
    return next(c["id"] for c in cases if c["application_id"] == application_id)


# ---------------------------------------------------------------- gate: required docs verified


async def test_move_to_policy_login_blocked_until_every_required_doc_verified(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN", "Aadhaar"])
    _headers, application_id = await _submitted_application(
        client, mock_db, product, mobile="9640000001", extra_doc_ids=product["document_type_ids"][1:]
    )
    case_id = await _case_for(client, owner_headers, application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)

    # Neither doc verified yet.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 409
    assert "PAN" in r.json()["error"]["message"] or "Aadhaar" in r.json()["error"]["message"]

    docs = (await client.get(f"/api/v1/applications/{application_id}/documents", headers=owner_headers)).json()["data"]
    await client.patch(f"/api/v1/applications/{application_id}/documents/{docs[0]['id']}/verify", headers=owner_headers)

    # One still outstanding.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 409

    await client.patch(f"/api/v1/applications/{application_id}/documents/{docs[1]['id']}/verify", headers=owner_headers)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_login"


async def test_front_back_required_doc_needs_both_sides_verified(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(
        mock_db, product_name="Senior Citizen Health", docs=["Aadhaar Card"], front_back=("Aadhaar Card",)
    )
    # Register + upload front & back.
    mobile = "9640000002"
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "FB Test"}, headers=headers)
    r = await client.post("/api/v1/applications", json={"product_category": "insurance", "product_id": product["product_id"]}, headers=headers)
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 1}}, headers=headers)
    doc_id = product["document_type_id"]
    for side in ("front", "back"):
        up = await client.post(
            f"/api/v1/applications/{application_id}/documents/upload-url",
            json={"document_type_id": doc_id, "file_name": f"{side}.jpg"}, headers=headers,
        )
        await client.post(
            f"/api/v1/applications/{application_id}/documents",
            json={"document_type_id": doc_id, "file_name": f"{side}.jpg", "s3_key": up.json()["data"]["s3_key"], "side": side},
            headers=headers,
        )
    await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)

    case_id = await _case_for(client, owner_headers, application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)

    docs = (await client.get(f"/api/v1/applications/{application_id}/documents", headers=owner_headers)).json()["data"]
    # Verify only the front.
    front = next(d for d in docs if d["side"] == "front")
    await client.patch(f"/api/v1/applications/{application_id}/documents/{front['id']}/verify", headers=owner_headers)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 409  # back still unverified

    back = next(d for d in docs if d["side"] == "back")
    await client.patch(f"/api/v1/applications/{application_id}/documents/{back['id']}/verify", headers=owner_headers)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- product change


async def test_change_product_re_resolves_schema_and_keeps_uploads(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    a = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    b = await _insurance_product_with_schema(mock_db, product_name="Senior Citizen Health", docs=["PAN", "Age Proof"])
    _headers, application_id = await _submitted_application(client, mock_db, a, mobile="9640000003")
    case_id = await _case_for(client, owner_headers, application_id)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/change-product", json={"product_id": b["product_id"]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["product_id"] == b["product_id"]

    # The Application's pinned schema followed the product.
    app_detail = (await client.get(f"/api/v1/applications/{application_id}", headers=owner_headers)).json()["data"]
    assert app_detail["product_id"] == b["product_id"]

    # The already-uploaded PAN is still there (not deleted).
    docs = (await client.get(f"/api/v1/applications/{application_id}/documents", headers=owner_headers)).json()["data"]
    assert len(docs) == 1


async def test_change_product_rejected_when_target_has_no_schema(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    a = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    schemaless_id = str(
        (await mock_db["insurance_products"].insert_one(
            InsuranceProduct(name="No Schema Plan", category_id=a["category_id"]).model_dump(by_alias=True, exclude={"id"})
        )).inserted_id
    )
    _headers, application_id = await _submitted_application(client, mock_db, a, mobile="9640000004")
    case_id = await _case_for(client, owner_headers, application_id)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/change-product", json={"product_id": schemaless_id}, headers=owner_headers
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- reject → re-eligibility schedule (all options)


@pytest.mark.parametrize(
    ("choice", "months"),
    [("3_months", 3), ("6_months", 6), ("12_months", 12)],
)
async def test_reject_schedules_re_eligibility_for_each_fixed_period(client, mock_db, owner_headers, choice, months):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name=f"Plan {choice}", docs=["PAN"])
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile=f"964100{months:04d}")
    case_id = await _case_for(client, owner_headers, application_id)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject", json={"reason": "x", "re_eligibility": choice}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]["insurance_details"]
    assert d["re_eligibility_choice"] == choice
    assert d["re_eligible_date"] is not None
    assert d["re_eligibility_auto_transitioned"] is False


async def test_reject_custom_date_validation(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Custom Plan", docs=["PAN"])
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9641009999")
    case_id = await _case_for(client, owner_headers, application_id)

    # Custom with no date → 422, and the case must NOT have been rejected (validation
    # happens before the transition).
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject", json={"reason": "x", "re_eligibility": "custom"}, headers=owner_headers
    )
    assert r.status_code == 422
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]["current_status"] == "fresh_lead"

    # Past date → 422.
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject",
        json={"reason": "x", "re_eligibility": "custom", "re_eligible_date": "2020-01-01"}, headers=owner_headers,
    )
    assert r.status_code == 422
    # Unknown option → 422 (schema validator: insurance offers 3/6/12/custom/no, not 9).
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject", json={"reason": "x", "re_eligibility": "9_months"}, headers=owner_headers
    )
    assert r.status_code == 422
    # A valid future custom date works.
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject",
        json={"reason": "x", "re_eligibility": "custom", "re_eligible_date": "2027-06-01"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["insurance_details"]["re_eligibility_choice"] == "custom"


# ---------------------------------------------------------------- re-eligible restart


async def test_re_eligible_case_restarts_at_fresh_lead_or_policy_document(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Term Life", category_name="Life Insurance", docs=["PAN"])
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9640000005")
    case_id = await _case_for(client, owner_headers, application_id)

    await client.post(
        f"/api/v1/insurance-cases/{case_id}/reject", json={"reason": "Cooling off", "re_eligibility": "3_months"}, headers=owner_headers
    )
    # The `auto_transition_re_eligible_cases` worker (Phase 4) flips rejected -> re_eligible
    # on the scheduled date; simulate that end state directly.
    await mock_db["application_workflows"].update_one(
        {"_id": ObjectId(case_id)}, {"$set": {"current_status": "re_eligible"}}
    )

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/restart", json={"target": "policy_document"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"


# ---------------------------------------------------------------- migration


async def test_migration_remaps_live_cases_and_rewrites_definitions(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    # Simulate a legacy case mid-pipeline on an old status.
    await mock_db["application_workflows"].insert_one({
        "case_code": "AFS-INS-000999", "case_type": "insurance", "application_id": "app-legacy",
        "customer_id": "cust-legacy", "product_id": "p", "product_category": "insurance",
        "current_status": "premium_acceptance", "on_hold_previous_status": "underwriting",
        "is_deleted": False, "version": 1,
    })
    await mock_db["workflow_definitions"].insert_one({
        "case_type": "insurance", "status": "underwriting", "label": "Underwriting", "sequence": 3,
        "allowed_next_statuses": [], "allowed_previous_statuses": [], "audit_event": "x", "is_deleted": False, "version": 1,
    })

    await _rewrite_definitions(mock_db)
    await _remap_cases(mock_db)

    case = await mock_db["application_workflows"].find_one({"case_code": "AFS-INS-000999"})
    assert case["current_status"] == "policy_login"  # premium_acceptance -> policy_login
    assert case["on_hold_previous_status"] == "policy_document"  # underwriting -> policy_document

    assert await mock_db["workflow_definitions"].find_one({"case_type": "insurance", "status": "underwriting"}) is None
    assert await mock_db["workflow_definitions"].find_one({"case_type": "insurance", "status": "policy_document"}) is not None


# ---------------------------------------------------------------- Phase 5: insurance-scoped per-document actions


async def test_insurance_scoped_verify_reject_wrappers_drive_the_gate(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(
        mock_db, product_name="Family Health Plus", docs=["PAN", "Extra Proof"], optional=("Extra Proof",)
    )
    _headers, application_id = await _submitted_application(
        client, mock_db, product, mobile="9642000001", extra_doc_ids=product["document_type_ids"][1:]
    )
    case_id = await _case_for(client, owner_headers, application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)

    listed = (await client.get(f"/api/v1/insurance-cases/{case_id}/documents", headers=owner_headers)).json()["data"]
    assert len(listed) == 2
    assert all(d["is_in_schema"] for d in listed)
    pan = next(d for d in listed if d["document_type_name"] == "PAN")
    extra = next(d for d in listed if d["document_type_name"] == "Extra Proof")

    # Reject the optional doc via the insurance wrapper — must NOT block the move.
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/{extra['id']}/reject",
        json={"reason": "blurry"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "rejected"

    # Required PAN still unverified -> blocked.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 409

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/{pan['id']}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"

    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_change_product_orphan_document_flagged_not_in_schema(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    a = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["Old Proof"])
    b = await _insurance_product_with_schema(mock_db, product_name="Senior Citizen Health", docs=["New Proof"])
    _headers, application_id = await _submitted_application(client, mock_db, a, mobile="9642000003")
    case_id = await _case_for(client, owner_headers, application_id)

    await client.post(f"/api/v1/insurance-cases/{case_id}/change-product", json={"product_id": b["product_id"]}, headers=owner_headers)

    docs = (await client.get(f"/api/v1/insurance-cases/{case_id}/documents", headers=owner_headers)).json()["data"]
    assert len(docs) == 1  # the upload was preserved
    assert docs[0]["is_in_schema"] is False  # its type is not in the new schema


async def test_case_document_history_wrapper_returns_all_versions(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9642000004")
    case_id = await _case_for(client, owner_headers, application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)

    doc_type_id = product["document_type_id"]
    doc = (await client.get(f"/api/v1/insurance-cases/{case_id}/documents", headers=owner_headers)).json()["data"][0]
    await client.post(
        f"/api/v1/insurance-cases/{case_id}/documents/{doc['id']}/reject", json={"reason": "redo"}, headers=owner_headers
    )
    # Customer re-uploads -> supersede -> a second row for the same type.
    up = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": doc_type_id, "file_name": "v2.pdf"}, headers=customer_headers,
    )
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": doc_type_id, "file_name": "v2.pdf", "s3_key": up.json()["data"]["s3_key"]},
        headers=customer_headers,
    )

    history = (
        await client.get(f"/api/v1/insurance-cases/{case_id}/documents/{doc_type_id}/history", headers=owner_headers)
    ).json()["data"]
    assert len(history) >= 2


# ---------------------------------------------------------------- Phase 5: "Add Other Document"


async def test_add_other_document_full_lifecycle(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    customer_headers, application_id = await _submitted_application(client, mock_db, product, mobile="9642000005")
    case_id = await _case_for(client, owner_headers, application_id)
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-document", headers=owner_headers)

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents", json={"name": "Previous Policy Copy"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    other_id = r.json()["data"]["id"]
    assert r.json()["data"]["document_status"] == "requested"

    # Customer sees the request and uploads.
    mine = (await client.get(f"/api/v1/insurance-cases/mine/{case_id}/other-documents", headers=customer_headers)).json()["data"]
    assert [d["id"] for d in mine] == [other_id]
    up = await client.post(
        f"/api/v1/insurance-cases/mine/{case_id}/other-documents/{other_id}/upload-url",
        json={"file_name": "policy.pdf"}, headers=customer_headers,
    )
    assert up.status_code == 200, up.text
    r = await client.post(
        f"/api/v1/insurance-cases/mine/{case_id}/other-documents/{other_id}/confirm",
        json={"file_name": "policy.pdf"}, headers=customer_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "uploaded"

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/other-documents/{other_id}/verify", headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"

    # Unverified "Other Documents" do NOT block the pipeline (only schema-required docs do).
    await _verify_all_current_documents(client, owner_headers, application_id)
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/other-documents", json={"name": "Extra"}, headers=owner_headers)
    assert r.status_code == 200
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-policy-login", headers=owner_headers)
    assert r.status_code == 200, r.text


async def test_add_other_document_rejected_outside_document_stages(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    _headers, application_id = await _submitted_application(client, mock_db, product, mobile="9642000006")
    case_id = await _case_for(client, owner_headers, application_id)

    # Still at fresh_lead.
    r = await client.post(f"/api/v1/insurance-cases/{case_id}/other-documents", json={"name": "Too early"}, headers=owner_headers)
    assert r.status_code == 409
