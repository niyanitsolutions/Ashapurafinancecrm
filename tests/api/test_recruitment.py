"""End-to-end tests for Insurance Advisor Recruitment.

Covers the 2026 flat recruitment stage machine (Fresh / BOP / Doc Collection / Exam Fee
Status / Examination / Re-Examination / Agency Code / Rejected), document collection with
a backend-enforced completeness gate (Doc Collection cannot be saved / completed until
every required document is present — brief §3/§14), the Exam Fee Status -> Examination
step, examination outcomes (PASS -> Advisor, FAIL/ABSENT -> Re-Examination, remarks
required), duplicate-transition prevention, the tab counts endpoint, the Profession
dropdown values, and permission gating on insurance_management:recruitment.
"""

import pytest

API = "/api/v1/recruitment-leads"


# ---------------------------------------------------------------- fixtures / helpers


async def _source_id(mock_db) -> str:
    from app.features.system_settings.models import LeadSource

    result = await mock_db["lead_sources"].insert_one(LeadSource(name="Referral").model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


def _payload(source_id, mobile="9876543210", **overrides):
    body = {
        "full_name": "Ravi Kumar",
        "mobile": mobile,
        "email": "ravi@example.com",
        "gender": "male",
        "age": 32,
        "source_id": source_id,
        "profession": "salaried",
        "remarks": "Interested in becoming an insurance advisor",
    }
    body.update(overrides)
    return body


async def _create(client, headers, source_id, **overrides):
    r = await client.post(API, json=_payload(source_id, **overrides), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _to_doc_collection(client, headers, source_id, **overrides):
    lead = await _create(client, headers, source_id, **overrides)
    lid = lead["id"]
    assert (await client.post(f"{API}/{lid}/move-to-bop", headers=headers)).status_code == 200
    r = await client.post(f"{API}/{lid}/move-to-doc-collection", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["stage"] == "doc_collection"
    return lid


async def _pay_exam_fee(client, headers, lid, **body):
    r = await client.post(f"{API}/{lid}/exam-fee", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["stage"] == "examination"
    return lid


async def _to_examination(client, headers, source_id, **overrides):
    """Fresh -> BOP -> Doc Collection -> (all docs saved) -> Exam Fee Status -> Examination."""
    lid = await _to_doc_collection(client, headers, source_id, **overrides)
    await _collect_full_documents(client, headers, lid)
    return await _pay_exam_fee(client, headers, lid)


async def _upload(client, headers, lid, slot, file_name="file.pdf"):
    r = await client.post(f"{API}/{lid}/documents/upload-url", json={"slot": slot, "file_name": file_name}, headers=headers)
    assert r.status_code == 200, r.text
    return {"s3_key": r.json()["data"]["s3_key"], "file_name": file_name}


async def _collect_full_documents(client, headers, lid, *, bank_proof_type="cheque", signature=None):
    body = {
        "pan": await _upload(client, headers, lid, "pan", "pan.jpg"),
        "aadhaar": await _upload(client, headers, lid, "aadhaar", "aadhaar.jpg"),
        "bank_proof": await _upload(client, headers, lid, "bank_proof", "cheque.jpg"),
        "qualification": await _upload(client, headers, lid, "qualification", "degree.pdf"),
        "photo": await _upload(client, headers, lid, "photo", "photo.jpg"),
        "bank_proof_type": bank_proof_type,
        "cheque_name_confirmed": bank_proof_type == "cheque",
        "email": "ravi@example.com",
        "mobile": "9876543210",
        "alternate_number": "9123456780",
        "nominee": {"name": "Priya Kumar", "dob": "1995-08-15", "relationship": "spouse"},
        "signature": signature or {"method": "type", "value": "Ravi Kumar"},
    }
    r = await client.put(f"{API}/{lid}/documents", json=body, headers=headers)
    assert r.status_code == 200, r.text
    # A complete document set completes Doc Collection and advances to Exam Fee Status.
    assert r.json()["data"]["stage"] == "exam_fee_status"
    return r.json()["data"]


# ---------------------------------------------------------------- create / validation


async def test_create_fresh_lead(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    assert lead["stage"] == "fresh"
    assert lead["recruitment_code"].startswith("AFS-RCT-")
    assert lead["source_name"] == "Referral"


async def test_create_requires_other_profession_when_other(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    r = await client.post(API, json=_payload(source_id, profession="other"), headers=owner_headers)
    assert r.status_code == 422
    r = await client.post(API, json=_payload(source_id, profession="other", other_profession="Farmer"), headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["other_profession"] == "Farmer"


async def test_profession_dropdown_values(client, mock_db, owner_headers):
    """Brief §8-10: Profession is House Wife / Retired / Self Employed / Salaried / Other —
    a separate concept from the advisor QR/Non-QR channel, stored and echoed verbatim."""
    source_id = await _source_id(mock_db)
    for i, profession in enumerate(["house_wife", "retired", "self_employed", "salaried"]):
        r = await client.post(
            API, json=_payload(source_id, mobile=f"980000200{i}", profession=profession), headers=owner_headers
        )
        assert r.status_code == 200, (profession, r.text)
        assert r.json()["data"]["profession"] == profession
    # The Individual/Employee advisor classification is NOT a valid profession.
    r = await client.post(API, json=_payload(source_id, profession="employee"), headers=owner_headers)
    assert r.status_code == 422


async def test_create_rejects_bad_enums_and_missing_fields(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    for bad in ({"gender": "m"}, {"profession": "student"}, {"mobile": "12345"}, {"age": 5}, {"full_name": ""}):
        r = await client.post(API, json=_payload(source_id, **bad), headers=owner_headers)
        assert r.status_code == 422, (bad, r.text)


async def test_create_rejects_unknown_source(client, owner_headers):
    r = await client.post(API, json=_payload("64b0c0000000000000000000"), headers=owner_headers)
    assert r.status_code == 422


async def test_duplicate_active_mobile_blocked_rejected_allowed(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    first = await _create(client, owner_headers, source_id)
    dup = await client.post(API, json=_payload(source_id), headers=owner_headers)
    assert dup.status_code == 409
    # Reject the first, then the same mobile is free again.
    assert (await client.post(f"{API}/{first['id']}/reject", json={"reason": "no"}, headers=owner_headers)).status_code == 200
    assert (await client.post(API, json=_payload(source_id), headers=owner_headers)).status_code == 200


# ---------------------------------------------------------------- fresh actions


async def test_save_keeps_lead_in_fresh(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    r = await client.patch(f"{API}/{lead['id']}", json={"remarks": "called, keen"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "fresh"
    assert r.json()["data"]["remarks"] == "called, keen"


async def test_save_and_move_to_bop(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lead['id']}/move-to-bop", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "bop"
    listed = await client.get(f"{API}?stage=bop", headers=owner_headers)
    assert [x["id"] for x in listed.json()["data"]] == [lead["id"]]
    fresh = await client.get(f"{API}?stage=fresh", headers=owner_headers)
    assert fresh.json()["data"] == []


async def test_reject_from_fresh(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lead['id']}/reject", json={"reason": "not eligible"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "rejected"
    assert r.json()["data"]["rejected_reason"] == "not eligible"
    r = await client.post(f"{API}/{lead['id']}/reject", json={"reason": "again"}, headers=owner_headers)
    assert r.status_code == 409  # already rejected


async def test_move_to_bop_requires_fresh(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    await client.post(f"{API}/{lead['id']}/move-to-bop", headers=owner_headers)
    r = await client.post(f"{API}/{lead['id']}/move-to-bop", headers=owner_headers)
    assert r.status_code == 409


# ---------------------------------------------------------------- BOP actions


async def test_bop_back_to_fresh(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    await client.post(f"{API}/{lead['id']}/move-to-bop", headers=owner_headers)
    r = await client.post(f"{API}/{lead['id']}/back-to-fresh", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "fresh"
    # No duplication.
    assert (await client.get(f"{API}?stage=fresh", headers=owner_headers)).json()["meta"]["pagination"]["total"] == 1


async def test_bop_to_doc_collection(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    listed = await client.get(f"{API}?stage=doc_collection", headers=owner_headers)
    assert [x["id"] for x in listed.json()["data"]] == [lid]


async def test_doc_collection_requires_bop(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lead['id']}/move-to-doc-collection", headers=owner_headers)
    assert r.status_code == 409


# ---------------------------------------------------------------- documents


async def test_document_collection_full_roundtrip(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    data = await _collect_full_documents(client, owner_headers, lid)
    docs = data["documents"]
    assert docs["pan"]["file_name"] == "pan.jpg"
    assert docs["pan"]["download_url"]
    assert docs["bank_proof_type"] == "cheque"
    assert docs["cheque_name_confirmed"] is True
    assert docs["nominee"]["relationship"] == "spouse"
    assert data["documents_ready"] is True


async def test_incomplete_documents_block_save(client, mock_db, owner_headers):
    """Brief §3/§14: the backend must refuse to save/complete Doc Collection until every
    required document is present — an API client cannot bypass the gate."""
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    r = await client.put(
        f"{API}/{lid}/documents",
        json={"pan": await _upload(client, owner_headers, lid, "pan", "pan.jpg"), "mobile": "9876543210"},
        headers=owner_headers,
    )
    assert r.status_code == 422
    assert "all required documents" in r.text.lower()
    # The lead never left Doc Collection.
    assert (await client.get(f"{API}/{lid}", headers=owner_headers)).json()["data"]["stage"] == "doc_collection"


async def test_cheque_without_name_confirmation_blocks_save(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    body = {
        "pan": await _upload(client, owner_headers, lid, "pan", "pan.jpg"),
        "aadhaar": await _upload(client, owner_headers, lid, "aadhaar", "aadhaar.jpg"),
        "bank_proof": await _upload(client, owner_headers, lid, "bank_proof", "cheque.jpg"),
        "qualification": await _upload(client, owner_headers, lid, "qualification", "degree.pdf"),
        "photo": await _upload(client, owner_headers, lid, "photo", "photo.jpg"),
        "bank_proof_type": "cheque",
        "cheque_name_confirmed": False,
        "signature": {"method": "type", "value": "Ravi Kumar"},
    }
    r = await client.put(f"{API}/{lid}/documents", json=body, headers=owner_headers)
    assert r.status_code == 422
    body["cheque_name_confirmed"] = True
    r = await client.put(f"{API}/{lid}/documents", json=body, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "exam_fee_status"


async def test_passbook_proof_needs_no_cheque_attestation(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    await _collect_full_documents(client, owner_headers, lid, bank_proof_type="passbook")
    await _pay_exam_fee(client, owner_headers, lid)
    r = await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "advisor"


@pytest.mark.parametrize(
    "signature",
    [
        {"method": "type", "value": "Ravi Kumar"},
        {"method": "draw", "value": "ignored", "file_name": "sig.png"},
        {"method": "upload", "value": "ignored", "file_name": "sign.jpg"},
    ],
)
async def test_signature_methods_store_single_active_representation(client, mock_db, owner_headers, signature):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    if signature["method"] in ("draw", "upload"):
        await _upload(client, owner_headers, lid, "signature", signature["file_name"])
    data = await _collect_full_documents(client, owner_headers, lid, signature=signature)
    stored = data["documents"]["signature"]
    assert stored["method"] == signature["method"]
    if signature["method"] == "type":
        assert stored["value"] == "Ravi Kumar"
    else:
        assert stored["value"].startswith("http")  # presigned download URL, exactly one


async def test_draw_signature_requires_file_name(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    r = await client.put(f"{API}/{lid}/documents", json={"signature": {"method": "draw", "value": "x"}}, headers=owner_headers)
    assert r.status_code == 422


async def test_documents_cannot_be_saved_outside_doc_collection(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    r = await client.put(f"{API}/{lead['id']}/documents", json={"mobile": "9876543210"}, headers=owner_headers)
    assert r.status_code == 409


# ---------------------------------------------------------------- examination


async def test_exam_fee_advances_doc_complete_lead(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    await _collect_full_documents(client, owner_headers, lid)
    # Guarded before Exam Fee Status.
    dc = await _to_doc_collection(client, owner_headers, source_id, mobile="9800001111")
    assert (await client.post(f"{API}/{dc}/exam-fee", json={}, headers=owner_headers)).status_code == 409

    r = await client.post(f"{API}/{lid}/exam-fee", json={"reference": "UTR-77"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "examination"
    assert r.json()["data"]["exam_fee_paid"] is True
    assert r.json()["data"]["exam_fee_reference"] == "UTR-77"


async def test_examination_pass_promotes_to_advisor_once(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)

    r = await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "advisor"
    assert r.json()["data"]["advisor_id"]

    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": lid}) == 1
    advisor = await client.get(f"{API}/{lid}/advisor", headers=owner_headers)
    assert advisor.json()["data"]["full_name"] == "Ravi Kumar"
    assert advisor.json()["data"]["advisor_code"].startswith("AFS-ADV-")


async def test_examination_cannot_be_recorded_before_examination_stage(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_doc_collection(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    assert r.status_code == 409


async def test_examination_fail_requires_remarks_and_moves_to_re_examination(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lid}/examination", json={"result": "fail"}, headers=owner_headers)
    assert r.status_code == 422
    r = await client.post(f"{API}/{lid}/examination", json={"result": "fail", "remarks": "did not clear"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "re_examination"
    assert r.json()["data"]["examinations"][-1]["remarks"] == "did not clear"


async def test_examination_absent_requires_remarks_and_moves_to_re_examination(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lid}/examination", json={"result": "absent"}, headers=owner_headers)
    assert r.status_code == 422
    r = await client.post(f"{API}/{lid}/examination", json={"result": "absent", "remarks": "not present"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "re_examination"


async def test_re_examination_pass_promotes_to_advisor(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    await client.post(f"{API}/{lid}/examination", json={"result": "fail", "remarks": "retry"}, headers=owner_headers)
    r = await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "advisor"
    assert len(r.json()["data"]["examinations"]) == 2
    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": lid}) == 1


async def test_reject_allowed_from_mid_stages(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lid}/reject", json={"reason": "withdrew"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["stage"] == "rejected"


async def test_duplicate_pass_and_manual_move_never_duplicate_advisor(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)

    # Manual move after auto-promotion is a no-op, not a second advisor.
    r = await client.post(f"{API}/{lid}/move-to-advisor", headers=owner_headers)
    assert r.status_code == 200
    # A replayed examination on a promoted lead is rejected outright.
    r = await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    assert r.status_code == 409
    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": lid}) == 1


async def test_manual_move_to_advisor_requires_pass(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    r = await client.post(f"{API}/{lid}/move-to-advisor", headers=owner_headers)
    assert r.status_code == 409
    await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)
    # ...but after a real PASS the lead is already promoted; manual move stays idempotent.
    r = await client.post(f"{API}/{lid}/move-to-advisor", headers=owner_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------- counts / timeline


async def test_counts_reflect_stage_distribution(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    await _create(client, owner_headers, source_id, mobile="9800000001")
    bop = await _create(client, owner_headers, source_id, mobile="9800000002")
    await client.post(f"{API}/{bop['id']}/move-to-bop", headers=owner_headers)
    await _to_doc_collection(client, owner_headers, source_id, mobile="9800000003")
    fee = await _to_doc_collection(client, owner_headers, source_id, mobile="9800000004")
    await _collect_full_documents(client, owner_headers, fee)  # -> exam_fee_status
    reexam = await _to_examination(client, owner_headers, source_id, mobile="9800000005")
    await client.post(f"{API}/{reexam}/examination", json={"result": "fail", "remarks": "x"}, headers=owner_headers)

    counts = (await client.get(f"{API}/counts", headers=owner_headers)).json()["data"]
    assert counts["fresh"] == 1
    assert counts["bop"] == 1
    assert counts["doc_collection"] == 1
    assert counts["exam_fee_status"] == 1
    assert counts["examination"] == 0
    assert counts["re_examination"] == 1


async def test_agency_code_tab_lists_promoted_candidates(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lid = await _to_examination(client, owner_headers, source_id)
    await client.post(f"{API}/{lid}/examination", json={"result": "pass"}, headers=owner_headers)

    listed = await client.get(f"{API}?stage=agency_code", headers=owner_headers)
    assert [x["id"] for x in listed.json()["data"]] == [lid]
    counts = (await client.get(f"{API}/counts", headers=owner_headers)).json()["data"]
    assert counts["agency_code"] == 1


async def test_timeline_records_transitions(client, mock_db, owner_headers):
    source_id = await _source_id(mock_db)
    lead = await _create(client, owner_headers, source_id)
    await client.post(f"{API}/{lead['id']}/move-to-bop", headers=owner_headers)
    entries = (await client.get(f"{API}/{lead['id']}/timeline", headers=owner_headers)).json()["data"]
    event_types = {e["event_type"] for e in entries if e["type"] == "activity"}
    assert {"created", "moved_to_bop"} <= event_types


# ---------------------------------------------------------------- permissions


async def _employee(client, owner_headers, master_data, mobile="9500000021"):
    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Rec", "last_name": "Ruiter",
            "email": f"rec{mobile}@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-15", "employment_type": "full_time",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _recruitment_permission_id(client, owner_headers) -> str:
    r = await client.post(
        "/api/v1/permissions",
        json={"module": "insurance_management", "resource": "recruitment", "actions": ["view", "create", "edit", "assign", "approve"]},
        headers=owner_headers,
    )
    if r.status_code == 200:
        return r.json()["data"]["id"]
    existing = await client.get("/api/v1/permissions", headers=owner_headers)
    return next(p["id"] for p in existing.json()["data"] if p["module"] == "insurance_management" and p["resource"] == "recruitment")


async def _grant(client, owner_headers, employee_id, actions, role_name):
    perm_id = await _recruitment_permission_id(client, owner_headers)
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    grants = [{"permission_id": perm_id, "granted_actions": actions}] if actions else []
    await client.put(f"/api/v1/roles/{role_id}/permissions", json={"grants": grants}, headers=owner_headers)
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _login(client, mobile, password="InitialPass1!"):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_employee_without_permission_is_forbidden(client, mock_db, owner_headers, master_data):
    source_id = await _source_id(mock_db)
    emp = await _employee(client, owner_headers, master_data)
    await _grant(client, owner_headers, emp["id"], [], role_name="No Access")
    headers = await _login(client, "9500000021")
    assert (await client.get(API, headers=headers)).status_code == 403
    assert (await client.post(API, json=_payload(source_id), headers=headers)).status_code == 403


async def test_employee_sees_only_own_or_assigned(client, mock_db, owner_headers, master_data):
    source_id = await _source_id(mock_db)
    emp = await _employee(client, owner_headers, master_data, mobile="9500000031")
    await _grant(client, owner_headers, emp["id"], ["view", "create", "edit"], role_name="Recruiter")
    headers = await _login(client, "9500000031")

    mine = await _create(client, headers, source_id, mobile="9700000001")
    await _create(client, owner_headers, source_id, mobile="9700000002")  # owner's, not visible

    listed = await client.get(API, headers=headers)
    assert [x["id"] for x in listed.json()["data"]] == [mine["id"]]


async def test_employee_with_assign_has_broad_visibility(client, mock_db, owner_headers, master_data):
    source_id = await _source_id(mock_db)
    emp = await _employee(client, owner_headers, master_data, mobile="9500000041")
    await _grant(client, owner_headers, emp["id"], ["view", "assign"], role_name="Recruit Lead")
    headers = await _login(client, "9500000041")

    await _create(client, owner_headers, source_id, mobile="9700000011")
    listed = await client.get(API, headers=headers)
    assert listed.json()["meta"]["pagination"]["total"] == 1
