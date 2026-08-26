"""Production fix "DC vs LM" — a Lead-less application (no Lead ever created, e.g. a
customer applying directly through the Customer Portal) must now sit in Document
Collection, submitted-but-unmoved, exactly like a Lead-originated one, until Staff
explicitly moves it — instead of the old behavior (decision #130) where it became
visible in Loan Management immediately at submission with no staging at all. This file
covers the Lead-less half end to end; `test_leads.py`'s existing `test_move_to_loan_
management_*` suite already covers the Lead-originated half (unaffected, verified as a
regression below).

Reuses `test_leads.py`'s own fixtures/helpers (`_lead_master_data`, `_create_employee`,
`_create_lead`, `_login`, `_grant_leads_view_create`, `_seed_document_type`,
`_seed_form_definition`, `_seed_application`, `_seed_document`,
`_seed_loan_new_customer_definition`) rather than re-implementing them.
"""

from app.features.system_settings.models import LoanProduct
from test_leads import (
    _create_employee,
    _create_lead,
    _grant_leads_view_create,
    _lead_master_data,
    _login,
    _seed_application,
    _seed_document,
    _seed_document_type,
    _seed_form_definition,
    _seed_loan_new_customer_definition,
)


async def _register_customer(client, mobile: str) -> dict:
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    dev_otp = r.json()["data"]["dev_otp"]
    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": dev_otp, "purpose": "signup"})
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": "CustomerPass1!"})
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": "CustomerPass1!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _upload_and_confirm(client, headers, application_id: str, doc_type_id: str):
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": doc_type_id, "file_name": "doc.pdf"},
        headers=headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": doc_type_id, "file_name": "doc.pdf", "s3_key": s3_key}, headers=headers,
    )


async def _submit_lead_less_application(client, lmd, *, mobile: str, doc_type_id: str, product_id: str | None = None) -> tuple[dict, str]:
    """Lead-less (Flow 2): customer registers directly, no Lead ever created, applies
    for the loan product, uploads its one required document (left `pending`, i.e. NOT
    yet verified — callers verify it themselves if the scenario needs that), and
    submits. Returns (customer_headers, application_id)."""
    customer_headers = await _register_customer(client, mobile)
    r = await client.post("/api/v1/customers/me", json={"full_name": "Direct Applicant"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/applications", json={"product_category": "loan", "product_id": product_id or lmd["loan_product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    assert not r.json()["data"].get("lead_id")

    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    await _upload_and_confirm(client, customer_headers, application_id, doc_type_id)
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    return customer_headers, application_id


async def _verify_document(mock_db, *, application_id: str, doc_type_id: str, verifier_id: str = "000000000000000000000001"):
    await mock_db["application_documents"].update_one(
        {"application_id": application_id, "document_type_id": doc_type_id, "is_current": True},
        {"$set": {"verification_status": "verified", "verified_by": verifier_id}},
    )


# ---------------------------------------------------------------------- 1-4: core lifecycle


async def test_lead_less_submitted_application_appears_in_dc_not_in_lm(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170001", doc_type_id=doc_type_id)

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["application_id"] == application_id)
    assert row["is_lead_less"] is True
    assert row["application_status"] == "submitted"

    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert all(c["application_id"] != application_id for c in r.json()["data"])


async def test_lead_less_partially_verified_application_stays_in_dc(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    second_doc_type_id = await _seed_document_type(mock_db, "Aadhaar")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id, second_doc_type_id])
    customer_headers = await _register_customer(client, "9611170002")
    await client.post("/api/v1/customers/me", json={"full_name": "Direct Applicant"}, headers=customer_headers)
    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": lmd["loan_product_id"]}, headers=customer_headers)
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    # Both required documents uploaded (needed to pass the submission gate), but only
    # the first is verified — required-documents-verified is still incomplete.
    await _upload_and_confirm(client, customer_headers, application_id, doc_type_id)
    await _upload_and_confirm(client, customer_headers, application_id, second_doc_type_id)
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 422, r.text

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert any(x["application_id"] == application_id for x in r.json()["data"])
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert all(c["application_id"] != application_id for c in r.json()["data"])


async def test_lead_less_fully_verified_but_not_moved_stays_in_dc(client, mock_db, owner_headers, master_data):
    """The "don't auto-move" rule — 100% of required documents verified must NOT, on
    its own, move the application into Loan Management."""
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170003", doc_type_id=doc_type_id)
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert any(x["application_id"] == application_id for x in r.json()["data"])
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert all(c["application_id"] != application_id for c in r.json()["data"])


async def test_lead_less_moved_application_disappears_from_dc_appears_in_lm_never_both(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170004", doc_type_id=doc_type_id)
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)

    r = await client.get(f"/api/v1/leads/document-collection/applications/{application_id}/summary", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["all_documents_verified"] is True

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    dc_ids = {x["application_id"] for x in r.json()["data"]}
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    lm_ids = {c["application_id"] for c in r.json()["data"]}
    assert application_id not in dc_ids
    assert application_id in lm_ids
    assert not (application_id in dc_ids and application_id in lm_ids)


# ---------------------------------------------------------------------- 5: same customer, two applications


async def test_same_customer_one_application_in_lm_another_in_dc(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    business_loan_id = str(
        (await mock_db["loan_products"].insert_one(LoanProduct(name="Business Loan").model_dump(by_alias=True, exclude={"id"}))).inserted_id
    )
    await _seed_form_definition(mock_db, "loan", business_loan_id, document_type_ids=[doc_type_id])

    customer_headers, personal_loan_app_id = await _submit_lead_less_application(client, lmd, mobile="9611170005", doc_type_id=doc_type_id)
    await _verify_document(mock_db, application_id=personal_loan_app_id, doc_type_id=doc_type_id)
    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{personal_loan_app_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": business_loan_id}, headers=customer_headers)
    assert r.status_code == 200, r.text
    business_loan_app_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{business_loan_app_id}", json={"form_data": {"loan_amount": 300000}}, headers=customer_headers)
    await _upload_and_confirm(client, customer_headers, business_loan_app_id, doc_type_id)
    r = await client.post(f"/api/v1/applications/{business_loan_app_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    dc_ids = {x["application_id"] for x in r.json()["data"]}
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    lm_ids = {c["application_id"] for c in r.json()["data"]}
    assert personal_loan_app_id in lm_ids and personal_loan_app_id not in dc_ids
    assert business_loan_app_id in dc_ids and business_loan_app_id not in lm_ids


# ---------------------------------------------------------------------- 7-8: counts consistency


async def test_dc_count_matches_dc_list_with_mixed_lead_and_lead_less_rows(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    form_def_id = await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])

    employee = await _create_employee(client, owner_headers, master_data, mobile="9788880099", email="dc-count@example.com")
    lead = await _create_lead(client, owner_headers, lmd, mobile="9611170010", assigned_to=employee["id"])
    r = await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    await _seed_application(
        mock_db, lead_id=lead["id"], form_definition_id=form_def_id, product_category="loan", product_id=lmd["loan_product_id"], status="draft"
    )
    await _submit_lead_less_application(client, lmd, mobile="9611170011", doc_type_id=doc_type_id)

    r = await client.get("/api/v1/leads/counts", headers=owner_headers)
    assert r.status_code == 200, r.text
    dc_count = r.json()["data"]["document_collection"]

    r = await client.get("/api/v1/leads?stage=document_collection&page_size=100", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert dc_count == len(r.json()["data"]) == r.json()["meta"]["pagination"]["total"]


async def test_lm_count_matches_lm_list_after_lead_less_move(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170012", doc_type_id=doc_type_id)
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)
    await client.post(f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers)

    r = await client.get("/api/v1/loan-cases/counts", headers=owner_headers)
    assert r.status_code == 200, r.text
    new_customer_count = r.json()["data"]["new_customer"]
    r = await client.get("/api/v1/loan-cases?status=new_customer&page_size=100", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert new_customer_count == len(r.json()["data"])


# ---------------------------------------------------------------------- 9: move action's own guards


async def test_move_lead_less_rejects_a_lead_originated_application(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    form_def_id = await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])

    employee = await _create_employee(client, owner_headers, master_data, mobile="9788880098", email="lead-guard@example.com")
    lead = await _create_lead(client, owner_headers, lmd, mobile="9611170013", assigned_to=employee["id"])
    await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    application_id = await _seed_application(
        mock_db, lead_id=lead["id"], form_definition_id=form_def_id, product_category="loan", product_id=lmd["loan_product_id"], status="submitted"
    )
    await _seed_document(mock_db, application_id=application_id, document_type_id=doc_type_id, verification_status="verified")

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


async def test_move_lead_less_rejects_before_submission(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    customer_headers = await _register_customer(client, "9611170014")
    await client.post("/api/v1/customers/me", json={"full_name": "Draft Applicant"}, headers=customer_headers)
    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": lmd["loan_product_id"]}, headers=customer_headers)
    application_id = r.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


async def test_move_lead_less_enforces_assignment_scoping_for_employee(client, mock_db, owner_headers, master_data):
    """An Employee with `leads:leads:edit` may only move a Lead-less application
    currently assigned to them — mirrors `set_stage`'s own assignment-scoping exactly."""
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170015", doc_type_id=doc_type_id)
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)
    # Left unassigned (`assigned_to=None`) — a non-Owner Employee must be denied.

    employee = await _create_employee(client, owner_headers, master_data, mobile="9788880097", email="scoping@example.com")
    await _grant_leads_view_create(client, owner_headers, employee["id"])
    employee_headers = await _login(client, "9788880097")

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=employee_headers
    )
    assert r.status_code == 403, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": employee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=employee_headers
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- 10-11: Document Required (already-implemented, regression coverage)


async def test_optional_document_does_not_block_lead_less_submission_or_move(client, mock_db, owner_headers, master_data):
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition
    from app.features.customer.constants import FieldType

    required_doc_type_id = await _seed_document_type(mock_db, "PAN")
    optional_doc_type_id = await _seed_document_type(mock_db, "Passport")
    from app.features.customer.models import RequiredDocumentDefinition

    form_def = ApplicationFormDefinition(
        product_category="loan", product_id=lmd["loan_product_id"],
        fields=[FormFieldDefinition(key="loan_amount", label="Loan Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[
            RequiredDocumentDefinition(document_type_id=required_doc_type_id, required=True),
            RequiredDocumentDefinition(document_type_id=optional_doc_type_id, required=False),
        ],
        status="active",
    )
    await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))

    # Passport (optional) never uploaded at all.
    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170016", doc_type_id=required_doc_type_id)
    await _verify_document(mock_db, application_id=application_id, doc_type_id=required_doc_type_id)

    r = await client.get(f"/api/v1/leads/document-collection/applications/{application_id}/summary", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["documents_required"] == 1  # only the required one counts
    assert r.json()["data"]["all_documents_verified"] is True

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 200, r.text


async def test_required_document_defaults_true_for_legacy_schema_missing_the_field(client, mock_db, owner_headers, master_data):
    """Backward compatibility (Part 19): a `RequiredDocumentDefinition` written before
    the `required` field existed (a raw dict with no `required` key at all) must still
    behave as required, not silently become optional."""
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition
    from app.features.customer.constants import FieldType

    doc_type_id = await _seed_document_type(mock_db, "PAN")
    form_def = ApplicationFormDefinition(
        product_category="loan", product_id=lmd["loan_product_id"],
        fields=[FormFieldDefinition(key="loan_amount", label="Loan Amount", field_type=FieldType.NUMBER, required=True)],
        status="active",
    )
    payload = form_def.model_dump(by_alias=True, exclude={"id"})
    # Simulate a legacy stored document with no `required` key at all.
    payload["required_documents"] = [{"document_type_id": doc_type_id}]
    await mock_db["application_form_definitions"].insert_one(payload)

    _customer_headers, application_id = await _submit_lead_less_application(client, lmd, mobile="9611170017", doc_type_id=doc_type_id)
    # Document uploaded but left unverified — legacy-required document must still block.
    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- 6: Lead-originated regression (unaffected by this fix)


async def test_lead_originated_lifecycle_still_correct_after_lead_less_fix(client, mock_db, owner_headers, master_data):
    """Regression — the pre-existing, already-correct Lead-originated path must behave
    identically after this fix (its own gate/query paths are untouched)."""
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    form_def_id = await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id])
    employee = await _create_employee(client, owner_headers, master_data, mobile="9788880096", email="lead-regression@example.com")
    lead = await _create_lead(client, owner_headers, lmd, mobile="9611170018", assigned_to=employee["id"])
    await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    application_id = await _seed_application(
        mock_db, lead_id=lead["id"], customer_id="000000000000000000000077", form_definition_id=form_def_id,
        product_category="loan", product_id=lmd["loan_product_id"], status="submitted",
    )
    await _seed_document(mock_db, application_id=application_id, document_type_id=doc_type_id, verification_status="verified")

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    row = next(x for x in r.json()["data"] if x["id"] == lead["id"])
    assert row["is_lead_less"] is False

    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert all(c["application_id"] != application_id for c in r.json()["data"])

    r = await client.post(f"/api/v1/leads/{lead['id']}/stage", json={"stage": "loan_management"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/leads?stage=document_collection", headers=owner_headers)
    assert all(x["id"] != lead["id"] for x in r.json()["data"])
    r = await client.get("/api/v1/loan-cases?unassigned_only=true", headers=owner_headers)
    assert any(c["application_id"] == application_id for c in r.json()["data"])


# ---------------------------------------------------------------------- "I don't have this document" x DC/LM gate


async def test_lead_less_move_succeeds_with_a_not_available_required_document(client, mock_db, owner_headers, master_data):
    """"I don't have this document" production fix: a required document the customer
    declared not-available now satisfies the Lead-less Move to Loan Management gate
    exactly like a verified one — but the summary must never report it as verified."""
    await _seed_loan_new_customer_definition(mock_db)
    lmd = await _lead_master_data(mock_db)
    doc_type_id = await _seed_document_type(mock_db, "PAN")
    second_doc_type_id = await _seed_document_type(mock_db, "Bank Statement")
    await _seed_form_definition(mock_db, "loan", lmd["loan_product_id"], document_type_ids=[doc_type_id, second_doc_type_id])

    customer_headers = await _register_customer(client, "9611170020")
    r = await client.post("/api/v1/customers/me", json={"full_name": "Direct Applicant"}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/applications", json={"product_category": "loan", "product_id": lmd["loan_product_id"]}, headers=customer_headers)
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000}}, headers=customer_headers)
    await _upload_and_confirm(client, customer_headers, application_id, doc_type_id)
    # Bank Statement (also required) declared not-available BEFORE submission — the
    # submission gate must treat this as accounted-for, not as a missing document.
    r = await client.post(
        f"/api/v1/applications/{application_id}/documents/{second_doc_type_id}/not-available", headers=customer_headers
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text
    await _verify_document(mock_db, application_id=application_id, doc_type_id=doc_type_id)

    r = await client.get(f"/api/v1/leads/document-collection/applications/{application_id}/summary", headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["documents_verified"] == 1
    assert data["documents_not_available"] == 1
    assert data["all_documents_verified"] is True

    r = await client.post(
        f"/api/v1/leads/document-collection/applications/{application_id}/move-to-loan-management", json={}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
