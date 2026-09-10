"""End-to-end tests for Advisor Management (Phase 2).

Covers the Advisor list + its three independent filters (Profession / Type / Status),
QR / Non-QR "Type", the Advisor detail (with linked recruitment info), Add Business, and
the policy-count / total-premium aggregation from the saved business records.
"""

from app.features.system_settings.models import LeadSource

RECRUIT = "/api/v1/recruitment-leads"
ADV = "/api/v1/advisors"


async def _source_id(mock_db) -> str:
    result = await mock_db["lead_sources"].insert_one(LeadSource(name="Referral").model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _promote_advisor(client, headers, mock_db, *, mobile="9876543210", profession="salaried") -> dict:
    """Run a recruitment lead all the way to examination PASS and return its Advisor."""
    source_id = await _source_id(mock_db)
    body = {
        "full_name": "Ravi Kumar", "mobile": mobile, "email": "ravi@example.com", "gender": "male",
        "age": 32, "source_id": source_id, "profession": profession,
    }
    if profession == "other":
        body["other_profession"] = "Farmer"
    lead = (await client.post(RECRUIT, json=body, headers=headers)).json()["data"]
    lid = lead["id"]
    assert (await client.post(f"{RECRUIT}/{lid}/move-to-bop", headers=headers)).status_code == 200
    assert (await client.post(f"{RECRUIT}/{lid}/move-to-doc-collection", headers=headers)).status_code == 200

    async def upload(slot, name):
        r = await client.post(f"{RECRUIT}/{lid}/documents/upload-url", json={"slot": slot, "file_name": name}, headers=headers)
        return {"s3_key": r.json()["data"]["s3_key"], "file_name": name}

    docs = {
        "pan": await upload("pan", "pan.jpg"),
        "aadhaar": await upload("aadhaar", "aadhaar.jpg"),
        "bank_proof": await upload("bank_proof", "passbook.jpg"),
        "qualification": await upload("qualification", "degree.pdf"),
        "photo": await upload("photo", "photo.jpg"),
        "bank_proof_type": "passbook",
        "nominee": {"name": "Priya", "dob": "1995-08-15", "relationship": "spouse"},
        "signature": {"method": "type", "value": "Ravi Kumar"},
        "mobile": mobile,
    }
    assert (await client.put(f"{RECRUIT}/{lid}/documents", json=docs, headers=headers)).status_code == 200
    assert (await client.post(f"{RECRUIT}/{lid}/exam-fee", json={}, headers=headers)).status_code == 200
    r = await client.post(f"{RECRUIT}/{lid}/examination", json={"result": "pass"}, headers=headers)
    assert r.status_code == 200, r.text
    advisor = (await client.get(f"{RECRUIT}/{lid}/advisor", headers=headers)).json()["data"]
    return advisor


# ---------------------------------------------------------------- list / detail


async def test_promoted_advisor_appears_in_non_qr_list(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    r = await client.get(f"{ADV}?channel=non_qr", headers=owner_headers)
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()["data"]]
    assert advisor["id"] in ids
    row = next(a for a in r.json()["data"] if a["id"] == advisor["id"])
    assert row["channel"] == "non_qr"
    assert row["no_of_policies"] == 0
    assert row["total_premium"] == 0

    qr = await client.get(f"{ADV}?channel=qr", headers=owner_headers)
    assert advisor["id"] not in [a["id"] for a in qr.json()["data"]]


async def test_advisor_detail_includes_linked_recruitment(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    r = await client.get(f"{ADV}/{advisor['id']}", headers=owner_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["recruitment"]["full_name"] == "Ravi Kumar"
    assert data["recruitment"]["stage"] == "advisor"
    assert data["recruitment"]["documents"]["pan"]["file_name"] == "pan.jpg"
    assert data["businesses"] == []


# ---------------------------------------------------------------- explicit QR / Non-QR type


async def test_type_is_explicit_and_decoupled_from_agency_code(client, mock_db, owner_headers):
    """Brief §2/§6: QR vs Non-QR ("Type") is an explicit staff choice on the Agency Code
    edit form — NOT derived from the agency code. Editing the Type re-classifies the same
    advisor without minting a duplicate."""
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    # Setting an agency code alone does NOT flip the channel.
    r = await client.patch(f"{ADV}/{aid}", json={"agency_code": "AG-1001", "agent_code": "AGT-9"}, headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["data"]["channel"] == "non_qr"
    assert r.json()["data"]["agency_code"] == "AG-1001"
    assert r.json()["data"]["agent_code"] == "AGT-9"

    # Explicitly choosing QR moves the advisor to the QR roster.
    r = await client.patch(f"{ADV}/{aid}", json={"channel": "qr"}, headers=owner_headers)
    assert r.json()["data"]["channel"] == "qr"
    assert aid in [a["id"] for a in (await client.get(f"{ADV}?channel=qr", headers=owner_headers)).json()["data"]]
    assert aid not in [a["id"] for a in (await client.get(f"{ADV}?channel=non_qr", headers=owner_headers)).json()["data"]]

    # Flipping back to Non-QR keeps the same advisor id (no duplicate).
    r = await client.patch(f"{ADV}/{aid}", json={"channel": "non_qr"}, headers=owner_headers)
    assert r.json()["data"]["channel"] == "non_qr"
    assert r.json()["data"]["id"] == aid
    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": advisor["recruitment_lead_id"]}) == 1

    # A QR advisor may still carry no agency code, and a Non-QR advisor may keep one.
    assert (await client.patch(f"{ADV}/{aid}", json={"channel": "qr", "agency_code": ""}, headers=owner_headers)).json()["data"]["channel"] == "qr"


async def test_agent_code_and_password_are_write_safe(client, mock_db, owner_headers):
    """Password is hashed, never returned in any response, and never written in plaintext
    to the audit log."""
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    r = await client.patch(f"{ADV}/{aid}", json={"agent_code": "AGT-777", "password": "S3cretPass!"}, headers=owner_headers)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["agent_code"] == "AGT-777"
    assert "password" not in body
    assert "password_hash" not in body

    # Detail + list + summary never leak the field either.
    for payload in (
        (await client.get(f"{ADV}/{aid}", headers=owner_headers)).json()["data"],
        next(a for a in (await client.get(ADV, headers=owner_headers)).json()["data"] if a["id"] == aid),
    ):
        assert "password" not in payload and "password_hash" not in payload

    stored = await mock_db["advisors"].find_one({"_id": __import__("bson").ObjectId(aid)})
    assert stored["password_hash"] and stored["password_hash"] != "S3cretPass!"

    audits = await mock_db["audit_logs"].find({"event_type": "recruitment_advisor_updated"}).to_list(length=50)
    assert audits
    for a in audits:
        assert "S3cretPass!" not in str(a)
        assert "password_hash" not in a.get("metadata", {})


async def test_short_password_accepted_and_hashed(client, mock_db, owner_headers):
    """The Agency Code password field has NO minimum-length / complexity policy — a short
    value like "123" is accepted, stored only as a bcrypt hash, and never echoed back."""
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    for pw in ("123", "12345", "abc"):
        r = await client.patch(f"{ADV}/{aid}", json={"password": pw}, headers=owner_headers)
        assert r.status_code == 200, (pw, r.text)
        body = r.json()["data"]
        assert "password" not in body and "password_hash" not in body

    from app.security.password import verify_password

    stored = await mock_db["advisors"].find_one({"_id": __import__("bson").ObjectId(aid)})
    assert stored["password_hash"].startswith("$2") and stored["password_hash"] != "abc"
    assert verify_password("abc", stored["password_hash"])


async def test_blank_password_preserves_existing(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    await client.patch(f"{ADV}/{aid}", json={"password": "123"}, headers=owner_headers)
    original = (await mock_db["advisors"].find_one({"_id": __import__("bson").ObjectId(aid)}))["password_hash"]

    # A blank password + another field change must NOT touch the stored hash.
    await client.patch(f"{ADV}/{aid}", json={"password": "", "agent_code": "AGT-1"}, headers=owner_headers)
    after_blank = (await mock_db["advisors"].find_one({"_id": __import__("bson").ObjectId(aid)}))["password_hash"]
    assert after_blank == original

    # ...and so must omitting the field entirely.
    await client.patch(f"{ADV}/{aid}", json={"agency_code": "AG-9"}, headers=owner_headers)
    assert (await mock_db["advisors"].find_one({"_id": __import__("bson").ObjectId(aid)}))["password_hash"] == original


async def test_status_update_and_filter(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    # Active -> Inactive: the advisor stays in the DB, only status flips.
    assert (await client.patch(f"{ADV}/{aid}", json={"status": "inactive"}, headers=owner_headers)).json()["data"]["status"] == "inactive"
    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": advisor["recruitment_lead_id"]}) == 1

    active = await client.get(f"{ADV}?status=active", headers=owner_headers)
    assert aid not in [a["id"] for a in active.json()["data"]]
    inactive = await client.get(f"{ADV}?status=inactive", headers=owner_headers)
    assert [a["id"] for a in inactive.json()["data"]] == [aid]

    # Inactive -> Active restores it to the Active view (still one record).
    assert (await client.patch(f"{ADV}/{aid}", json={"status": "active"}, headers=owner_headers)).json()["data"]["status"] == "active"
    assert aid in [a["id"] for a in (await client.get(f"{ADV}?status=active", headers=owner_headers)).json()["data"]]
    assert await mock_db["advisors"].count_documents({"recruitment_lead_id": advisor["recruitment_lead_id"]}) == 1


# ---------------------------------------------------------------- Profession / Type / Status filters


async def test_profession_is_copied_from_the_lead_and_displayed(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db, profession="retired")
    row = next(a for a in (await client.get(ADV, headers=owner_headers)).json()["data"] if a["id"] == advisor["id"])
    assert row["profession"] == "retired"
    assert (await client.get(f"{ADV}/{advisor['id']}", headers=owner_headers)).json()["data"]["profession"] == "retired"


async def test_legacy_advisor_without_profession_still_loads_under_all(client, mock_db, owner_headers):
    """Backward compatibility: an advisor row stored before the profession field existed
    loads fine, shows `profession = null`, appears under "All", and is excluded from every
    specific profession filter (never guessed)."""
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    await mock_db["advisors"].update_one(
        {"_id": __import__("bson").ObjectId(aid)},
        {"$unset": {"profession": "", "other_profession": ""}},
    )

    row = next(a for a in (await client.get(ADV, headers=owner_headers)).json()["data"] if a["id"] == aid)
    assert row["profession"] is None
    assert (await client.get(f"{ADV}/{aid}", headers=owner_headers)).json()["data"]["profession"] is None
    assert aid not in [a["id"] for a in (await client.get(f"{ADV}?profession=salaried", headers=owner_headers)).json()["data"]]


async def test_profession_filter_each_bucket(client, mock_db, owner_headers):
    made = {
        p: (await _promote_advisor(client, owner_headers, mock_db, mobile=m, profession=p))["id"]
        for p, m in (
            ("house_wife", "9700000001"), ("retired", "9700000002"), ("self_employed", "9700000003"),
            ("salaried", "9700000004"), ("other", "9700000005"),
        )
    }
    for profession, aid in made.items():
        listed = await client.get(f"{ADV}?profession={profession}", headers=owner_headers)
        assert [a["id"] for a in listed.json()["data"]] == [aid], profession
        assert all(a["profession"] == profession for a in listed.json()["data"])

    # "All" (no profession param) returns every advisor.
    all_ids = {a["id"] for a in (await client.get(ADV, headers=owner_headers)).json()["data"]}
    assert set(made.values()) <= all_ids


async def test_type_filter(client, mock_db, owner_headers):
    qr = await _promote_advisor(client, owner_headers, mock_db, mobile="9700000011")
    non_qr = await _promote_advisor(client, owner_headers, mock_db, mobile="9700000012")
    await client.patch(f"{ADV}/{qr['id']}", json={"channel": "qr"}, headers=owner_headers)

    qr_list = await client.get(f"{ADV}?channel=qr", headers=owner_headers)
    assert [a["id"] for a in qr_list.json()["data"]] == [qr["id"]]
    non_qr_list = await client.get(f"{ADV}?channel=non_qr", headers=owner_headers)
    assert qr["id"] not in [a["id"] for a in non_qr_list.json()["data"]]
    assert non_qr["id"] in [a["id"] for a in non_qr_list.json()["data"]]


async def test_profession_type_status_combine(client, mock_db, owner_headers):
    # Rahul: Salaried / QR / Active   (the only full match for the 3-way filter below)
    rahul = await _promote_advisor(client, owner_headers, mock_db, mobile="9700000021", profession="salaried")
    await client.patch(f"{ADV}/{rahul['id']}", json={"channel": "qr"}, headers=owner_headers)
    # Kumar: Salaried / Non QR / Active
    await _promote_advisor(client, owner_headers, mock_db, mobile="9700000022", profession="salaried")
    # Arun: Salaried / QR / Inactive
    arun = await _promote_advisor(client, owner_headers, mock_db, mobile="9700000023", profession="salaried")
    await client.patch(f"{ADV}/{arun['id']}", json={"channel": "qr", "status": "inactive"}, headers=owner_headers)
    # Suresh: Retired / QR / Active
    suresh = await _promote_advisor(client, owner_headers, mock_db, mobile="9700000024", profession="retired")
    await client.patch(f"{ADV}/{suresh['id']}", json={"channel": "qr"}, headers=owner_headers)

    r = await client.get(f"{ADV}?profession=salaried&channel=qr&status=active", headers=owner_headers)
    assert [a["id"] for a in r.json()["data"]] == [rahul["id"]]

    # "All" is independent per filter: profession=All, Type=QR, Status=Active -> Rahul + Suresh.
    r = await client.get(f"{ADV}?channel=qr&status=active", headers=owner_headers)
    assert {a["id"] for a in r.json()["data"]} == {rahul["id"], suresh["id"]}

    # profession=Retired, Type=All, Status=All -> only Suresh.
    r = await client.get(f"{ADV}?profession=retired", headers=owner_headers)
    assert [a["id"] for a in r.json()["data"]] == [suresh["id"]]


async def test_unknown_filter_values_rejected(client, mock_db, owner_headers):
    await _promote_advisor(client, owner_headers, mock_db)
    assert (await client.get(f"{ADV}?profession=doctor", headers=owner_headers)).status_code == 422
    assert (await client.get(f"{ADV}?channel=sometype", headers=owner_headers)).status_code == 422
    assert (await client.get(f"{ADV}?status=paused", headers=owner_headers)).status_code == 422


# ---------------------------------------------------------------- Add Business + aggregation


async def _add_business(client, headers, aid, **overrides):
    body = {
        "product_category": "savings", "product_name": "ABC Guaranteed Savings", "premium": 50000,
        "ppt": 10, "pt": 20, "policy_issue_date": "2026-09-01", "comment": "Annual premium",
    }
    body.update(overrides)
    return await client.post(f"{ADV}/{aid}/business", json=body, headers=headers)


async def test_business_customer_fields_persist_and_old_rows_load(client, mock_db, owner_headers):
    """Brief §11-13: Add Business gains Customer Name / Customer Mobile / Policy Number.
    They persist and show in the list/detail after a refresh; pre-redesign rows (without
    the fields) still load and render as null."""
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    r = await _add_business(
        client, owner_headers, aid,
        customer_name="Anita Rao", customer_mobile="9812345678", policy_number="POL-42",
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["customer_name"] == "Anita Rao"
    assert r.json()["data"]["customer_mobile"] == "9812345678"
    assert r.json()["data"]["policy_number"] == "POL-42"

    # Insert a legacy business row with none of the new fields.
    from app.features.recruitment.models import AdvisorBusiness

    legacy = AdvisorBusiness(
        advisor_id=aid, product_category="savings", product_name="Legacy Plan",
        premium=1000, ppt=5, pt=10,
        policy_issue_date=__import__("datetime").datetime(2025, 1, 1, tzinfo=__import__("datetime").UTC),
    )
    doc = legacy.model_dump(by_alias=True, exclude={"id"})
    doc.pop("customer_name", None)
    doc.pop("customer_mobile", None)
    doc.pop("policy_number", None)
    await mock_db["advisor_business"].insert_one(doc)

    listed = (await client.get(f"{ADV}/{aid}/business", headers=owner_headers)).json()["data"]
    assert len(listed) == 2
    legacy_row = next(b for b in listed if b["product_name"] == "Legacy Plan")
    assert legacy_row["customer_name"] is None
    assert legacy_row["policy_number"] is None

    detail = (await client.get(f"{ADV}/{aid}", headers=owner_headers)).json()["data"]
    assert {b["customer_name"] for b in detail["businesses"]} == {"Anita Rao", None}


async def test_add_business_and_single_aggregate(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    r = await _add_business(client, owner_headers, aid)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["product_name"] == "ABC Guaranteed Savings"

    listed = await client.get(f"{ADV}/{aid}/business", headers=owner_headers)
    assert len(listed.json()["data"]) == 1

    detail = (await client.get(f"{ADV}/{aid}", headers=owner_headers)).json()["data"]
    assert detail["no_of_policies"] == 1
    assert detail["total_premium"] == 50000


async def test_multiple_businesses_aggregate(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    await _add_business(client, owner_headers, aid, product_category="savings", premium=50000)
    await _add_business(client, owner_headers, aid, product_category="protection", premium=25000)
    await _add_business(client, owner_headers, aid, product_category="ulip", premium=75000)

    detail = (await client.get(f"{ADV}/{aid}", headers=owner_headers)).json()["data"]
    assert detail["no_of_policies"] == 3
    assert detail["total_premium"] == 150000

    row = next(a for a in (await client.get(f"{ADV}?channel=non_qr", headers=owner_headers)).json()["data"] if a["id"] == aid)
    assert row["no_of_policies"] == 3
    assert row["total_premium"] == 150000


async def test_custom_category_requires_custom_name(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    r = await _add_business(client, owner_headers, aid, product_category="custom", custom_category=None)
    assert r.status_code == 422
    r = await _add_business(client, owner_headers, aid, product_category="custom", custom_category="Micro Insurance")
    assert r.status_code == 200
    assert r.json()["data"]["custom_category"] == "Micro Insurance"


async def test_business_validation(client, mock_db, owner_headers):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]
    for bad in ({"premium": -1}, {"ppt": 0}, {"pt": 0}, {"product_category": "whole_life"}, {"policy_issue_date": "not-a-date"}, {"product_name": ""}):
        r = await _add_business(client, owner_headers, aid, **bad)
        assert r.status_code == 422, (bad, r.text)


# ---------------------------------------------------------------- permissions


async def _employee(client, owner_headers, master_data, mobile="9500000061"):
    r = await client.post(
        "/api/v1/employees",
        json={
            "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Adv", "last_name": "Mgr",
            "email": f"adv{mobile}@example.com", "department_id": master_data["department_id"],
            "designation_id": master_data["designation_id"], "branch_id": master_data["branch_id"],
            "joining_date": "2026-01-15", "employment_type": "full_time",
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _grant(client, owner_headers, employee_id, actions, role_name):
    r = await client.post(
        "/api/v1/permissions",
        json={"module": "insurance_management", "resource": "recruitment", "actions": ["view", "create", "edit", "assign", "approve"]},
        headers=owner_headers,
    )
    if r.status_code == 200:
        perm_id = r.json()["data"]["id"]
    else:
        existing = await client.get("/api/v1/permissions", headers=owner_headers)
        perm_id = next(p["id"] for p in existing.json()["data"] if p["module"] == "insurance_management" and p["resource"] == "recruitment")
    role = await client.post("/api/v1/roles", json={"name": role_name}, headers=owner_headers)
    role_id = role.json()["data"]["id"]
    grants = [{"permission_id": perm_id, "granted_actions": actions}] if actions else []
    await client.put(f"/api/v1/roles/{role_id}/permissions", json={"grants": grants}, headers=owner_headers)
    await client.post(f"/api/v1/roles/{role_id}/assign", json={"employee_id": employee_id}, headers=owner_headers)


async def _login(client, mobile):
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": "InitialPass1!"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_permission_gating(client, mock_db, owner_headers, master_data):
    advisor = await _promote_advisor(client, owner_headers, mock_db)
    aid = advisor["id"]

    no_access = await _employee(client, owner_headers, master_data, mobile="9500000061")
    await _grant(client, owner_headers, no_access["id"], [], "Adv No Access")
    h = await _login(client, "9500000061")
    assert (await client.get(ADV, headers=h)).status_code == 403
    assert (await client.get(f"{ADV}/{aid}", headers=h)).status_code == 403
    assert (await client.patch(f"{ADV}/{aid}", json={"status": "inactive"}, headers=h)).status_code == 403
    assert (await _add_business(client, h, aid)).status_code == 403

    view_only = await _employee(client, owner_headers, master_data, mobile="9500000062")
    await _grant(client, owner_headers, view_only["id"], ["view"], "Adv View Only")
    h2 = await _login(client, "9500000062")
    assert (await client.get(ADV, headers=h2)).status_code == 200
    assert (await client.patch(f"{ADV}/{aid}", json={"status": "inactive"}, headers=h2)).status_code == 403
    assert (await _add_business(client, h2, aid)).status_code == 403
