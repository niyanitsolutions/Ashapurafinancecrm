"""Manual Insurance Lead creation ("+ Add Insurance Lead") + staff "Move To" stage
movement. Insurance-only; Loan is never exercised here. Every stage change goes through
the real `InsuranceCaseService` / `WorkflowEngine` layer and its gates.
"""

import pytest
from bson import ObjectId
from test_insurance_policy_leads import _insurance_product_with_schema
from test_workflow import _seed_workflow_definitions

_BASE = {
    "full_name": "Ravi Kumar",
    "mobile": "9876500001",
    "email": "ravi@example.com",
    "gender": "male",
    "age": 35,
    "profession": "Software Engineer",
    "annual_income": 800000,
    "remarks": "Interested in family health insurance",
}


def _payload(product, *, stage="fresh_lead", mobile="9876500001", **extra):
    return {
        **_BASE, "mobile": mobile,
        "insurance_category_id": product["category_id"], "product_id": product["product_id"],
        "stage": stage, **extra,
    }


async def _create(client, headers, product, **kw):
    return await client.post("/api/v1/insurance-cases/manual", json=_payload(product, **kw), headers=headers)


# ---------------------------------------------------------------- creation


async def test_create_manual_lead_at_fresh_lead_makes_a_case_never_a_lead(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])

    r = await _create(client, owner_headers, product, stage="fresh_lead")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["current_status"] == "fresh_lead"
    assert data["customer_name"] == "Ravi Kumar"

    wf = await mock_db["application_workflows"].find_one({"_id": ObjectId(data["id"])})
    assert wf["case_type"] == "insurance"
    assert await mock_db["leads"].count_documents({}) == 0  # NEVER a Lead


async def test_manual_lead_field_validation(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])

    r = await _create(client, owner_headers, product, full_name="")
    assert r.status_code == 422
    r = await _create(client, owner_headers, product, mobile="12345")
    assert r.status_code == 422
    r = await _create(client, owner_headers, product, age=5)
    assert r.status_code == 422


async def test_manual_lead_rejects_inactive_category(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    await mock_db["insurance_categories"].update_one(
        {"_id": ObjectId(product["category_id"])}, {"$set": {"status": "inactive"}}
    )
    r = await _create(client, owner_headers, product)
    assert r.status_code == 409


async def test_manual_lead_rejects_product_not_in_selected_category(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    a = await _insurance_product_with_schema(mock_db, product_name="Health Plan", docs=["PAN"])
    b = await _insurance_product_with_schema(mock_db, product_name="Life Plan", category_name="Life Insurance", docs=["PAN"])
    body = _payload(a)
    body["product_id"] = b["product_id"]  # product from a different category
    r = await client.post("/api/v1/insurance-cases/manual", json=body, headers=owner_headers)
    assert r.status_code == 422


async def test_manual_lead_rejects_product_without_schema(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    from app.features.system_settings.models import InsuranceCategory, InsuranceProduct

    cat_id = str((await mock_db["insurance_categories"].insert_one(
        InsuranceCategory(name="Motor").model_dump(by_alias=True, exclude={"id"})
    )).inserted_id)
    prod_id = str((await mock_db["insurance_products"].insert_one(
        InsuranceProduct(name="No Schema", category_id=cat_id).model_dump(by_alias=True, exclude={"id"})
    )).inserted_id)
    body = {**_BASE, "insurance_category_id": cat_id, "product_id": prod_id, "stage": "fresh_lead"}
    r = await client.post("/api/v1/insurance-cases/manual", json=body, headers=owner_headers)
    assert r.status_code == 422


async def test_create_manual_lead_at_policy_document(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Family Health Plus", docs=["PAN"])
    r = await _create(client, owner_headers, product, stage="policy_document")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"


@pytest.mark.parametrize(("choice", "months"), [("3_months", 3), ("6_months", 6), ("12_months", 12)])
async def test_create_manual_lead_at_rejected_schedules_re_eligibility(client, mock_db, owner_headers, choice, months):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name=f"Plan {choice}", docs=["PAN"])
    r = await _create(
        client, owner_headers, product, mobile=f"987650{months:04d}", stage="rejected",
        reason="Not eligible right now", re_eligibility=choice,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["current_status"] == "rejected"
    assert d["insurance_details"]["re_eligibility_choice"] == choice
    assert d["insurance_details"]["re_eligible_date"] is not None


async def test_create_manual_lead_at_rejected_no_re_eligibility(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    r = await _create(client, owner_headers, product, stage="rejected", reason="stop", re_eligibility="no")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["insurance_details"]["re_eligible_date"] is None


async def test_create_manual_lead_rejected_requires_reason(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    r = await _create(client, owner_headers, product, stage="rejected", re_eligibility="6_months")
    assert r.status_code == 422


async def test_create_manual_lead_invalid_custom_date_leaves_no_rows(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    wf_before = await mock_db["application_workflows"].count_documents({})
    app_before = await mock_db["applications"].count_documents({})
    users_before = await mock_db["users"].count_documents({})

    r = await _create(
        client, owner_headers, product, stage="rejected", reason="x",
        re_eligibility="custom", re_eligible_date="2020-01-01",
    )
    assert r.status_code == 422
    assert await mock_db["application_workflows"].count_documents({}) == wf_before
    assert await mock_db["applications"].count_documents({}) == app_before
    assert await mock_db["users"].count_documents({}) == users_before


async def test_create_manual_lead_at_re_eligible(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    r = await _create(
        client, owner_headers, product, stage="re_eligible", reason="cooling off", re_eligibility="3_months",
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"


async def test_manual_lead_reuses_existing_customer_for_same_mobile(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    r1 = await _create(client, owner_headers, product, mobile="9811111111")
    r2 = await _create(client, owner_headers, product, mobile="9811111111")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["customer_id"] == r2.json()["data"]["customer_id"]
    assert await mock_db["users"].count_documents({"mobile": "9811111111"}) == 1


async def test_manual_lead_unauthorized_employee(client, mock_db, employee_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _insurance_product_with_schema(mock_db, product_name="Plan", docs=["PAN"])
    r = await _create(client, employee_headers, product)
    assert r.status_code == 403


# ---------------------------------------------------------------- move to stage


async def _fresh_case(client, mock_db, owner_headers, *, mobile, docs=("PAN",), product_name="Plan"):
    product = await _insurance_product_with_schema(mock_db, product_name=product_name, docs=list(docs))
    r = await _create(client, owner_headers, product, mobile=mobile, stage="fresh_lead")
    assert r.status_code == 200, r.text
    return product, r.json()["data"]["id"]


async def test_move_to_stage_fresh_to_policy_document_writes_history(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000001")

    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_document"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "policy_document"

    timeline = (await client.get(f"/api/v1/insurance-cases/{case_id}/timeline", headers=owner_headers)).json()["data"]
    assert any(e.get("to_status") == "policy_document" for e in timeline)
    assert any("Staff moved this case" in (e.get("text") or "") for e in timeline)


async def test_move_to_stage_policy_login_blocked_until_docs_verified(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000002")

    # A manual lead has no documents — the Policy Login gate blocks the multi-hop move and
    # the case stops at the furthest stage it legally reached (Policy Document).
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_login"}, headers=owner_headers
    )
    assert r.status_code == 409
    assert "verified" in r.json()["error"]["message"].lower()
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]["current_status"] == "policy_document"


async def test_move_to_stage_policy_issued_blocked_without_premium(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000003")
    # Move as far forward as the gates allow — with no docs, the walk stops at Policy Document.
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_issued"}, headers=owner_headers
    )
    assert r.status_code == 409
    assert (await client.get(f"/api/v1/insurance-cases/{case_id}", headers=owner_headers)).json()["data"]["current_status"] == "policy_document"


async def test_move_to_stage_to_rejected_runs_reject_flow(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000004")
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage",
        json={"target": "rejected", "reason": "customer withdrew", "re_eligibility": "6_months"}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["current_status"] == "rejected"
    assert d["rejection_reason"] == "customer withdrew"
    assert d["insurance_details"]["re_eligible_date"] is not None


async def test_move_to_stage_rejected_requires_reason(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000005")
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "rejected"}, headers=owner_headers
    )
    assert r.status_code == 422


async def test_move_to_stage_rejected_to_re_eligible(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000006")
    await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage",
        json={"target": "rejected", "reason": "x", "re_eligibility": "no"}, headers=owner_headers,
    )
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "re_eligible"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "re_eligible"


async def test_move_to_stage_backward_policy_document_to_fresh_lead(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000007")
    await client.post(f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_document"}, headers=owner_headers)
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "fresh_lead"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["current_status"] == "fresh_lead"


async def test_move_to_stage_unauthorized_employee(client, mock_db, owner_headers, employee_headers):
    await _seed_workflow_definitions(mock_db)
    _product, case_id = await _fresh_case(client, mock_db, owner_headers, mobile="9822000008")
    r = await client.post(
        f"/api/v1/insurance-cases/{case_id}/move-to-stage", json={"target": "policy_document"}, headers=employee_headers
    )
    assert r.status_code == 403
