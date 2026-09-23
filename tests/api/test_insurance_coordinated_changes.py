"""Local mocked regression coverage for the coordinated Insurance changes."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId
from test_insurance_manual_lead import _create
from test_insurance_policy_leads import _insurance_product_with_schema
from test_recruitment_advisors import _promote_advisor, _source_id
from test_workflow import _seed_workflow_definitions

from app.features.bin.service import BinService
from app.security.encryption import decrypt


async def make_case(client, db, headers, docs):
    await _seed_workflow_definitions(db)
    product = await _insurance_product_with_schema(db, product_name="Test Insurance", docs=docs)
    response = await _create(client, headers, product)
    assert response.status_code == 200, response.text
    return response.json()["data"], product["document_type_ids"]


async def upload(client, headers, case_id, type_id, *, side=None, password=None, name=None):
    payload = {"document_type_id": type_id, "file_name": name or f"{side or 'single'}.pdf", "s3_key": "untrusted"}
    if side:
        payload["side"] = side
    if password is not None:
        payload["document_password"] = password
    response = await client.post(f"/api/v1/insurance-cases/{case_id}/documents/confirm", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("name", ["PAN Card", "Aadhaar Card", "Address Proof", "Bank Statement", "Cancelled Cheque", "Passport Size Photograph"])
@pytest.mark.parametrize("password", [None, "private-document-secret"])
async def test_optional_password_encryption_no_leaks_and_replacement(client, mock_db, owner_headers, employee_headers, caplog, name, password):
    case, types = await make_case(client, mock_db, owner_headers, [name])
    document = await upload(client, owner_headers, case["id"], types[0], password=password)
    stored = await mock_db["application_documents"].find_one({"_id": ObjectId(document["id"])})
    expected = password if name != "Passport Size Photograph" else None
    assert (decrypt(stored["password_encrypted"]) if stored["password_encrypted"] else None) == expected
    for path in (f"/api/v1/insurance-cases/{case['id']}", f"/api/v1/insurance-cases/{case['id']}/documents"):
        response = await client.get(path, headers=owner_headers)
        assert response.status_code == 200
        assert "password_encrypted" not in response.text
        assert "private-document-secret" not in response.text
    assert "private-document-secret" not in caplog.text
    assert "private-document-secret" not in json.dumps(await mock_db["audit_logs"].find({}).to_list(None), default=str)
    denied = await client.get(f"/api/v1/applications/{case['application_id']}/documents/{document['id']}/password", headers=employee_headers)
    assert denied.status_code == 403
    replacement = await upload(client, owner_headers, case["id"], types[0], name="replacement.pdf")
    assert replacement["has_password"] is False
    assert not (await mock_db["application_documents"].find_one({"_id": ObjectId(document["id"])}))["is_current"]


@pytest.mark.parametrize("sides,valid", [([None], True), (["front", "back"], True), (["front"], False), (["back"], False), ([], False)])
async def test_single_and_front_back_completion(client, mock_db, owner_headers, sides, valid):
    case, types = await make_case(client, mock_db, owner_headers, ["Aadhaar Card"])
    base = f"/api/v1/insurance-cases/{case['id']}"
    assert (await client.post(base + "/move-to-policy-document", headers=owner_headers)).status_code == 200
    for side in sides:
        doc = await upload(client, owner_headers, case["id"], types[0], side=side, password="pair-secret")
        assert doc["download_url"] and doc["attachment_url"]
        assert (await client.post(base + f"/documents/{doc['id']}/verify", headers=owner_headers)).status_code == 200
    response = await client.post(base + "/move-to-policy-login", headers=owner_headers)
    assert response.status_code == (200 if valid else 409), response.text


@pytest.mark.parametrize("indices", [[], [0], [1], [0, 1]])
async def test_bank_or_gate_and_summary(client, mock_db, owner_headers, indices):
    case, types = await make_case(client, mock_db, owner_headers, ["Bank Statement", "Cancelled Cheque"])
    base = f"/api/v1/insurance-cases/{case['id']}"
    await client.post(base + "/move-to-policy-document", headers=owner_headers)
    for index in indices:
        doc = await upload(client, owner_headers, case["id"], types[index])
        await client.post(base + f"/documents/{doc['id']}/verify", headers=owner_headers)
    detail = (await client.get(base, headers=owner_headers)).json()["data"]
    assert detail["required_documents"]["required_total"] == 1
    assert detail["required_documents"]["all_required_verified"] == bool(indices)
    response = await client.post(base + "/move-to-policy-login", headers=owner_headers)
    assert response.status_code == (200 if indices else 409), response.text


async def test_pair_replacement_shares_password_and_single_retires_pair(client, mock_db, owner_headers):
    case, types = await make_case(client, mock_db, owner_headers, ["PAN Card"])
    for side in ("front", "back"):
        await upload(client, owner_headers, case["id"], types[0], side=side, password="old")
    await upload(client, owner_headers, case["id"], types[0], side="front", password="new", name="new-front.pdf")
    docs = await mock_db["application_documents"].find({"application_id": case["application_id"], "is_current": True}).to_list(None)
    assert len(docs) == 2
    assert {decrypt(d["password_encrypted"]) for d in docs} == {"new"}
    await upload(client, owner_headers, case["id"], types[0], name="single-replacement.pdf")
    docs = await mock_db["application_documents"].find({"application_id": case["application_id"], "is_current": True}).to_list(None)
    assert len(docs) == 1 and docs[0]["side"] is None and docs[0]["password_encrypted"] is None


@pytest.mark.parametrize("stage", ["fresh_lead", "policy_document", "policy_login", "payment", "policy_issued", "rejected"])
async def test_manual_reeligible_preserves_history_and_schedule(client, mock_db, owner_headers, stage):
    case, _ = await make_case(client, mock_db, owner_headers, ["PAN Card"])
    await mock_db["application_workflows"].update_one({"_id": ObjectId(case["id"])}, {"$set": {
        "current_status": stage, "rejection_reason": "Historical rejection",
        "insurance_details.re_eligible_date": datetime(2026, 12, 1, tzinfo=UTC),
    }})
    before = await mock_db["application_status_history"].count_documents({"application_workflow_id": case["id"]})
    response = await client.post(f"/api/v1/insurance-cases/{case['id']}/move-to-stage", json={"target": "re_eligible"}, headers=owner_headers)
    if stage == "policy_issued":
        assert response.status_code == 409
        return
    assert response.status_code == 200, response.text
    stored = await mock_db["application_workflows"].find_one({"_id": ObjectId(case["id"])})
    assert stored["current_status"] == "re_eligible"
    assert stored["rejection_reason"] == "Historical rejection"
    assert stored["insurance_details"]["re_eligible_date"] is None
    assert stored["insurance_details"]["re_eligibility_auto_transitioned"] is False
    assert await mock_db["application_status_history"].count_documents({"application_workflow_id": case["id"]}) == before + 1
    again = await client.post(f"/api/v1/insurance-cases/{case['id']}/move-to-stage", json={"target": "re_eligible"}, headers=owner_headers)
    assert again.status_code == 200
    assert await mock_db["application_status_history"].count_documents({"application_workflow_id": case["id"]}) == before + 1


async def test_advisor_date_password_rbac_bin_and_reference_retention(client, mock_db, owner_headers, employee_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    base = f"/api/v1/advisors/{aid}"
    response = await client.patch(base, json={"joining_date": "2026-09-21", "password": "saved-secret", "channel": "qr"}, headers=owner_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["joining_date"].startswith("2026-09-20T18:30")
    await client.patch(base, json={"password": "", "status": "inactive", "channel": "non_qr"}, headers=owner_headers)
    assert (await client.get(base + "/password", headers=owner_headers)).json()["data"]["password"] == "saved-secret"
    assert (await client.get(base + "/password", headers=employee_headers)).status_code == 403
    assert (await client.patch(base, json={"status": "active"}, headers=employee_headers)).status_code == 403
    assert (await client.delete(f"/api/v1/bin/advisors/{aid}", headers=employee_headers)).status_code == 403
    response = await client.delete(f"/api/v1/bin/advisors/{aid}", headers=owner_headers)
    assert response.status_code == 200, response.text
    entry = response.json()["data"]
    assert (await client.get(base, headers=owner_headers)).status_code == 404
    await BinService(mock_db).purge_expired(datetime.now(UTC) + timedelta(days=40))
    assert await mock_db["advisors"].find_one({"_id": ObjectId(aid)}) is not None
    assert (await client.post(f"/api/v1/bin/{entry['id']}/restore", headers=owner_headers)).status_code == 200
    assert (await client.get(base, headers=owner_headers)).status_code == 200
    await mock_db["advisor_business"].insert_one({"advisor_id": aid})
    assert (await client.delete(f"/api/v1/bin/advisors/{aid}", headers=owner_headers)).status_code == 422


async def test_recruitment_owner_delete_restore(client, mock_db, owner_headers, employee_headers):
    source = await _source_id(mock_db)
    response = await client.post("/api/v1/recruitment-leads", json={"full_name": "Test Recruit", "mobile": "9876543210", "gender": "male", "age": 32, "source_id": source, "profession": "salaried"}, headers=owner_headers)
    lead = response.json()["data"]
    path = f"/api/v1/bin/recruitment_leads/{lead['id']}"
    assert (await client.delete(path, headers=employee_headers)).status_code == 403
    response = await client.delete(path, headers=owner_headers)
    assert response.status_code == 200, response.text
    entry = response.json()["data"]
    assert entry["record_code"] == lead["recruitment_code"]
    assert (await client.get(f"/api/v1/recruitment-leads/{lead['id']}", headers=owner_headers)).status_code == 404
    assert (await client.post(f"/api/v1/bin/{entry['id']}/restore", headers=owner_headers)).status_code == 200


async def test_employee_update_api_remains_owner_only(client, employee_headers):
    response = await client.patch(f"/api/v1/employees/{ObjectId()}", json={"first_name": "Changed"}, headers=employee_headers)
    assert response.status_code == 403
