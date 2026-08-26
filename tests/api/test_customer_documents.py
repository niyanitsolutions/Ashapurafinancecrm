"""Document Management redesign — Product Schema stays the single source of truth for
required/optional/hidden/allowed-types/max-size/multiple-upload, while the backend adds
real re-upload/versioning (supersede, not duplicate), an explicit "not available" state
for optional documents, and server-side enforcement of the schema's file-type/size/hidden
rules (previously advisory-only on the frontend). See docs/decisions and the plan this
implements for the full rationale.
"""

from app.features.customer.constants import FieldType
from app.features.customer.models import ApplicationFormDefinition, FormFieldDefinition, RequiredDocumentDefinition
from app.features.system_settings.models import DocumentType, LoanProduct
from app.features.workflow_engine.constants import CaseType, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition
from test_customer import _grant_customer_permission


async def _seed_workflow_definitions(mock_db):
    # A submitted Application lazily creates its Loan Case, which needs at least a
    # starting WorkflowDefinition row — see test_customer.py's identical helper.
    definition = WorkflowDefinition(
        case_type=CaseType.LOAN, status=LoanStatus.NEW_CUSTOMER, label="New Customer", sequence=1,
        allowed_next_statuses=[LoanStatus.DOCUMENTS_PENDING], audit_event=LoanAuditEvent.CASE_CREATED,
    )
    await mock_db["workflow_definitions"].insert_one(definition.model_dump(by_alias=True, exclude={"id"}))


async def _seed_rich_product_and_form(mock_db, *, product_name="Business Loan"):
    """A product with one of each document shape this feature needs to distinguish:
    a plain required doc (PAN), a required doc with type/size restrictions (GST), an
    optional doc (Trade Licence), a hidden doc (Internal Note), and a multiple-upload
    required doc (Income Proof)."""
    product = LoanProduct(name=product_name)
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    doc_ids: dict[str, str] = {}
    for key, name in [("pan", "PAN Card"), ("gst", "GST Certificate"), ("trade", "Trade Licence"), ("internal", "Internal Note"), ("income", "Income Proof")]:
        dt = DocumentType(name=f"{name}-{product_name}")
        doc_ids[key] = str((await mock_db["document_types"].insert_one(dt.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    required_documents = [
        RequiredDocumentDefinition(document_type_id=doc_ids["pan"], required=True),
        RequiredDocumentDefinition(document_type_id=doc_ids["gst"], required=True, allowed_types=["pdf"], max_size_mb=1),
        RequiredDocumentDefinition(document_type_id=doc_ids["trade"], required=False),
        RequiredDocumentDefinition(document_type_id=doc_ids["internal"], required=False, hidden=True),
        RequiredDocumentDefinition(document_type_id=doc_ids["income"], required=True, multiple_upload=True),
    ]
    form_def = ApplicationFormDefinition(
        product_category="loan",
        product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=required_documents,
        status="active",
    )
    form_def_id = (await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"product_category": "loan", "product_id": str(product_id), "form_definition_id": str(form_def_id), **{f"{k}_doc_id": v for k, v in doc_ids.items()}}


async def _create_employee(client, owner_headers, master_data, mobile, email):
    payload = {
        "mobile": mobile, "initial_password": "InitialPass1!", "first_name": "Staff", "last_name": "Member", "email": email,
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


async def _signup_via_otp(client, mobile: str, dev_otp: str, password: str = "CustomerPass1!") -> dict:
    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": dev_otp, "purpose": "signup"})
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": password})
    assert r.status_code == 200, r.text
    return await _login(client, mobile, password)


async def _start_application(client, product, *, mobile, full_name="Doc Test Customer"):
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    customer_headers = await _signup_via_otp(client, mobile, r.json()["data"]["dev_otp"])
    r = await client.post("/api/v1/customers/me", json={"full_name": full_name}, headers=customer_headers)
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    application_id = r.json()["data"]["id"]
    await client.patch(f"/api/v1/applications/{application_id}", json={"form_data": {"amount": 50000}}, headers=customer_headers)
    return customer_headers, application_id


async def _upload(client, application_id, doc_type_id, headers, *, file_name="doc.pdf", content_type="application/pdf", password=None, side=None):
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": doc_type_id, "file_name": file_name, "content_type": content_type}, headers=headers,
    )
    if upload.status_code != 200:
        return upload
    s3_key = upload.json()["data"]["s3_key"]
    payload = {"document_type_id": doc_type_id, "file_name": file_name, "s3_key": s3_key, "content_type": content_type}
    if password is not None:
        payload["password"] = password
    if side is not None:
        payload["side"] = side
    return await client.post(f"/api/v1/applications/{application_id}/documents", json=payload, headers=headers)


async def _seed_product_with_bank_statement(mock_db, *, product_name="Personal Loan", supports_password=True):
    """Bank Statement password support (Part 1A) — must work for every loan product
    whose schema references a document type flagged `supports_password`, without any
    per-product duplication. This seeds exactly that: one product, one document type."""
    product = LoanProduct(name=product_name)
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id

    bank_doc = DocumentType(name=f"Bank Statement-{product_name}", supports_password=supports_password)
    bank_doc_id = str((await mock_db["document_types"].insert_one(bank_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    form_def = ApplicationFormDefinition(
        product_category="loan",
        product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[RequiredDocumentDefinition(document_type_id=bank_doc_id, required=True)],
        status="active",
    )
    form_def_id = (await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {
        "product_category": "loan", "product_id": str(product_id), "bank_doc_id": bank_doc_id, "form_definition_id": str(form_def_id),
    }


async def _upload_all_required(client, application_id, product, headers):
    for doc_id in (product["pan_doc_id"], product["gst_doc_id"], product["income_doc_id"]):
        r = await _upload(client, application_id, doc_id, headers)
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- required/optional/submit gating


async def test_required_doc_missing_blocks_submit_uploading_allows_it(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000001")

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code >= 400, r.text
    assert "required document" in r.json()["error"]["message"].lower()

    await _upload_all_required(client, application_id, product, headers)
    # Trade Licence (optional) still untouched — submission must still succeed.
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "submitted"


async def test_optional_doc_can_be_marked_not_available_and_submit_succeeds(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000002")
    await _upload_all_required(client, application_id, product, headers)

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['trade_doc_id']}/not-available", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "not_available"

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code == 200, r.text


async def test_marking_a_required_document_not_available_is_allowed_and_submit_succeeds(client, mock_db, owner_headers):
    """"I don't have this document" production fix: a REQUIRED document may now also be
    declared unavailable (previously forbidden with 403) — submission proceeds treating
    it as accounted-for, distinct from verified. Only front/back and hidden documents
    still refuse this (see the dedicated tests for those)."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000003")
    # GST and Income Proof (both required) still genuinely uploaded — only PAN is waived.
    for doc_id in (product["gst_doc_id"], product["income_doc_id"]):
        r = await _upload(client, application_id, doc_id, headers)
        assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['pan_doc_id']}/not-available", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "not_available"

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code == 200, r.text


async def test_owner_flipping_optional_to_required_after_not_available_keeps_it_waivable(client, mock_db, owner_headers):
    """Regression for the schema-editing edge case this test module already covered:
    since required documents can now ALSO be marked not-available, flipping Trade
    Licence from optional to required for future applicants no longer needs to retract
    the waiver — a fresh applicant against the now-required schema can still declare it
    unavailable and submit."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000004")
    await _upload_all_required(client, application_id, product, headers)

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['trade_doc_id']}/not-available", headers=headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code == 200, r.text  # optional + not_available: submission succeeds

    # A second application against the same (now-edited) schema is the realistic
    # regression case — Owner flips Trade Licence to required for future applicants.
    r = await client.get(f"/api/v1/product-schemas?product_category=loan&product_id={product['product_id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    schema = next(s for s in r.json()["data"] if s["id"] == product["form_definition_id"])
    updated_docs = [
        {**{k: v for k, v in d.items() if k not in ("document_type_name", "source")}, "required": True} if d["document_type_id"] == product["trade_doc_id"] else
        {k: v for k, v in d.items() if k not in ("document_type_name", "source")}
        for d in schema["required_documents"]
    ]
    r = await client.patch(
        f"/api/v1/product-schemas/{product['form_definition_id']}", json={"required_documents": updated_docs}, headers=owner_headers
    )
    assert r.status_code == 200, r.text

    headers2, application_id2 = await _start_application(client, product, mobile="9800000014")
    await _upload_all_required(client, application_id2, product, headers2)
    r = await client.post(f"/api/v1/applications/{application_id2}/documents/{product['trade_doc_id']}/not-available", headers=headers2)
    assert r.status_code == 200, r.text  # now required — still waivable
    r = await client.post(f"/api/v1/applications/{application_id2}/submit", json={}, headers=headers2)
    assert r.status_code == 200, r.text  # accounted-for by the not-available declaration


async def test_verified_document_cannot_be_marked_not_available(client, mock_db, owner_headers):
    """Requirement: a customer must never be able to overwrite an already-VERIFIED
    document with a not-available declaration — that would silently erase a completed
    staff review. Re-upload/replacement must go through the authorized lifecycle."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000015")
    await _upload_all_required(client, application_id, product, headers)

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    assert r.status_code == 200, r.text
    pan_document_id = next(d["id"] for d in r.json()["data"] if d["document_type_id"] == product["pan_doc_id"])

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{pan_document_id}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['pan_doc_id']}/not-available", headers=headers)
    assert r.status_code == 403, r.text


async def test_verify_and_reject_refuse_a_not_available_document(client, mock_db, owner_headers):
    """Backend enforcement (not just the UI never offering Verify/Reject on a Not
    Available row): a document with no uploaded file can never be verified or rejected."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000016")
    await _upload_all_required(client, application_id, product, headers)

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['trade_doc_id']}/not-available", headers=headers)
    assert r.status_code == 200, r.text
    not_available_document_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{not_available_document_id}/verify", headers=owner_headers)
    assert r.status_code >= 400, r.text

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{not_available_document_id}/reject", json={"reason": "test"}, headers=owner_headers
    )
    assert r.status_code >= 400, r.text


async def test_staff_upload_over_not_available_document_stays_pending_then_verifiable(client, mock_db, owner_headers):
    """Staff can upload a document on a customer's behalf even after the customer
    declared it unavailable — the upload must clear the not-available state, land as
    pending (never auto-verified), and then follow the normal verify lifecycle."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000017")
    await _upload_all_required(client, application_id, product, headers)

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['trade_doc_id']}/not-available", headers=headers)
    assert r.status_code == 200, r.text

    r = await _upload(client, application_id, product["trade_doc_id"], owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["document_status"] == "uploaded"
    assert r.json()["data"]["verification_status"] == "pending"
    staff_uploaded_document_id = r.json()["data"]["id"]

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{staff_uploaded_document_id}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"


# ---------------------------------------------------------------------- hidden documents


async def test_hidden_document_upload_rejected_and_never_listed(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000005")

    r = await _upload(client, application_id, product["internal_doc_id"], headers)
    assert r.status_code >= 400, r.text

    r = await client.get(f"/api/v1/application-form-definitions?product_category=loan&product_id={product['product_id']}", headers=headers)
    assert r.status_code == 200, r.text
    type_ids = {d["document_type_id"] for d in r.json()["data"]["required_documents"] if not d.get("hidden")}
    assert product["internal_doc_id"] not in type_ids


# ---------------------------------------------------------------------- re-upload / versioning / multiple-upload


async def test_multiple_upload_false_supersedes_instead_of_duplicating(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000006")

    first = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_v1.pdf")
    assert first.status_code == 200, first.text
    second = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_v2.pdf")
    assert second.status_code == 200, second.text
    assert second.json()["data"]["doc_version"] == 2
    assert second.json()["data"]["replaces_document_id"] == first.json()["data"]["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    current_pan = [d for d in r.json()["data"] if d["document_type_id"] == product["pan_doc_id"]]
    assert len(current_pan) == 1
    assert current_pan[0]["file_name"] == "pan_v2.pdf"

    history = await client.get(f"/api/v1/applications/{application_id}/documents/{product['pan_doc_id']}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert [d["file_name"] for d in history.json()["data"]] == ["pan_v2.pdf", "pan_v1.pdf"]
    assert history.json()["data"][1]["is_current"] is False


async def test_multiple_upload_true_keeps_all_uploads_current(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000007")

    r1 = await _upload(client, application_id, product["income_doc_id"], headers, file_name="salary_jan.pdf")
    r2 = await _upload(client, application_id, product["income_doc_id"], headers, file_name="salary_feb.pdf")
    assert r1.status_code == 200 and r2.status_code == 200

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    income_docs = [d for d in r.json()["data"] if d["document_type_id"] == product["income_doc_id"]]
    assert len(income_docs) == 2
    assert all(d["is_current"] for d in income_docs)


# ---------------------------------------------------------------------- server-side type/size enforcement


async def test_disallowed_file_extension_rejected(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000008")

    r = await _upload(client, application_id, product["gst_doc_id"], headers, file_name="cert.exe", content_type="application/octet-stream")
    assert r.status_code >= 400, r.text


async def test_oversized_file_rejected(client, mock_db, monkeypatch, owner_headers):
    from app.features.customer import service as customer_service

    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000009")

    monkeypatch.setattr(customer_service, "get_object_size", lambda key: 2 * 1024 * 1024)  # GST's max_size_mb is 1
    r = await _upload(client, application_id, product["gst_doc_id"], headers, file_name="cert.pdf")
    assert r.status_code >= 400, r.text
    assert "size" in r.json()["error"]["message"].lower()


# ---------------------------------------------------------------------- authorization


async def test_customer_cannot_access_another_customers_documents(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers_a, application_id = await _start_application(client, product, mobile="9800000010")
    await _upload(client, application_id, product["pan_doc_id"], headers_a)

    headers_b, _ = await _start_application(client, product, mobile="9800000011")

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers_b)
    assert r.status_code == 403, r.text
    r = await _upload(client, application_id, product["pan_doc_id"], headers_b)
    assert r.status_code == 403, r.text


async def test_unassigned_employee_denied_assigned_employee_and_owner_allowed(client, mock_db, owner_headers, master_data):
    product = await _seed_rich_product_and_form(mock_db)
    customer_headers, application_id = await _start_application(client, product, mobile="9800000012")
    await _upload(client, application_id, product["pan_doc_id"], customer_headers)

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9500000021", email="bystander-doc@example.com")
    bystander_headers = await _login(client, "9500000021", "InitialPass1!")
    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=bystander_headers)
    assert r.status_code == 403, r.text
    r = await _upload(client, application_id, product["gst_doc_id"], bystander_headers)
    assert r.status_code == 403, r.text

    assignee = await _create_employee(client, owner_headers, master_data, mobile="9500000022", email="assignee-doc@example.com")
    r = await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": assignee["id"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assignee_headers = await _login(client, "9500000022", "InitialPass1!")

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=assignee_headers)
    assert r.status_code == 200, r.text
    r = await _upload(client, application_id, product["gst_doc_id"], assignee_headers, file_name="gst.pdf")
    assert r.status_code == 200, r.text  # staff re-upload/upload on an assigned application

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=owner_headers)
    assert r.status_code == 200, r.text  # Owner unrestricted


# ---------------------------------------------------------------------- Bank Statement password support


async def test_bank_statement_upload_without_password_succeeds(client, mock_db, owner_headers):
    """Scenario A - the password is genuinely optional; omitting it must never block
    upload, even for a document type that supports one."""
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan A")
    headers, application_id = await _start_application(client, product, mobile="9800000101")

    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["has_password"] is False


async def test_bank_statement_upload_with_password_succeeds_and_staff_can_reveal_it(client, mock_db, owner_headers):
    """Scenario B - a password-protected statement uploads successfully, is never
    echoed back in the confirm response, and an authorized staff member can retrieve
    the exact original value via the dedicated reveal endpoint."""
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan B")
    headers, application_id = await _start_application(client, product, mobile="9800000102")

    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="Secret@123")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["has_password"] is True
    assert "password" not in data
    document_id = data["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["password"] == "Secret@123"


async def test_password_never_appears_in_normal_get_or_list_responses(client, mock_db, owner_headers):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan C")
    headers, application_id = await _start_application(client, product, mobile="9800000103")
    await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="TopSecretNine")

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    assert r.status_code == 200, r.text
    assert "TopSecretNine" not in r.text
    assert "password_encrypted" not in r.text
    doc = r.json()["data"][0]
    assert doc["has_password"] is True
    assert "password" not in doc

    r = await client.get(f"/api/v1/applications/{application_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert "TopSecretNine" not in r.text


async def test_password_not_recorded_in_audit_log_metadata(client, mock_db, owner_headers):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan D")
    headers, application_id = await _start_application(client, product, mobile="9800000104")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="NeverLoggedOne")
    document_id = r.json()["data"]["id"]
    await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=owner_headers)

    logs = await mock_db["audit_logs"].find({}).to_list(length=200)
    for entry in logs:
        assert "NeverLoggedOne" not in str(entry.get("metadata", {}))
    event_types = {entry["event_type"] for entry in logs}
    assert "document_password_accessed" in event_types


async def test_employee_without_customer_edit_permission_cannot_reveal_password(client, mock_db, owner_headers, master_data):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan E")
    headers, application_id = await _start_application(client, product, mobile="9800000105")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="GuardedTwo")
    document_id = r.json()["data"]["id"]

    assignee = await _create_employee(client, owner_headers, master_data, mobile="9500000105", email="assignee-pw1@example.com")
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": assignee["id"]}, headers=owner_headers)
    assignee_headers = await _login(client, "9500000105", "InitialPass1!")

    # Assigned (can view/upload documents) but never granted customer:customers:edit -
    # same bar as verify/reject, and the reveal endpoint must enforce it too.
    r = await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=assignee_headers)
    assert r.status_code == 403, r.text


async def test_unassigned_employee_cannot_reveal_password_even_with_permission(client, mock_db, owner_headers, master_data):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan F")
    headers, application_id = await _start_application(client, product, mobile="9800000106")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="GuardedThree")
    document_id = r.json()["data"]["id"]

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9500000106", email="bystander-pw1@example.com")
    await _grant_customer_permission(client, owner_headers, bystander["id"], ["view", "edit"], role_name="Bystander Access")
    bystander_headers = await _login(client, "9500000106", "InitialPass1!")

    r = await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=bystander_headers)
    assert r.status_code == 403, r.text


async def test_assigned_employee_with_permission_can_reveal_password(client, mock_db, owner_headers, master_data):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan G")
    headers, application_id = await _start_application(client, product, mobile="9800000107")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="GuardedFour")
    document_id = r.json()["data"]["id"]

    assignee = await _create_employee(client, owner_headers, master_data, mobile="9500000107", email="assignee-pw2@example.com")
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": assignee["id"]}, headers=owner_headers)
    await _grant_customer_permission(client, owner_headers, assignee["id"], ["view", "edit"], role_name="Assignee Access")
    assignee_headers = await _login(client, "9500000107", "InitialPass1!")

    r = await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=assignee_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["password"] == "GuardedFour"


async def test_password_ignored_for_document_type_without_password_support(client, mock_db, owner_headers):
    """Defense in depth: even if a client sends a password for a document type NOT
    flagged supports_password, the backend silently drops it rather than persisting a
    value nobody asked to protect."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan No PW")
    headers, application_id = await _start_application(client, product, mobile="9800000108")

    r = await _upload(client, application_id, product["pan_doc_id"], headers, password="ShouldBeIgnored")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["has_password"] is False


async def test_reveal_password_404_when_document_has_no_password(client, mock_db, owner_headers):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan H")
    headers, application_id = await _start_application(client, product, mobile="9800000109")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf")
    document_id = r.json()["data"]["id"]

    r = await client.get(f"/api/v1/applications/{application_id}/documents/{document_id}/password", headers=owner_headers)
    assert r.status_code == 404, r.text


async def test_required_document_response_exposes_supports_password_flag(client, mock_db, owner_headers):
    """The upload UI's only signal for whether to show the optional password field -
    inherited from the DocumentType master-data flag, not duplicated per product."""
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan I")
    r = await client.get(
        "/api/v1/application-form-definitions", params={"product_category": "loan", "product_id": product["product_id"]}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    required = r.json()["data"]["required_documents"]
    assert required[0]["document_type_id"] == product["bank_doc_id"]
    assert required[0]["supports_password"] is True


# ---------------------------------------------------------------------- reject -> re-upload -> verify (decision #133)


async def test_reject_then_reupload_then_verify_full_sequence(client, mock_db, owner_headers):
    """The core "reject -> re-upload -> verify" flow: a rejected document is not deleted
    (kept as history), the replacement becomes the current, pending document, and staff
    can verify it — using the exact same generic upload/versioning machinery every
    re-upload already uses, not a special-cased "re-upload" endpoint."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Reject")
    headers, application_id = await _start_application(client, product, mobile="9800000201")

    first = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_old.jpg")
    assert first.status_code == 200, first.text
    document_id = first.json()["data"]["id"]

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject",
        json={"reason": "PAN card image is unclear."}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "rejected"
    assert r.json()["data"]["rejection_reason"] == "PAN card image is unclear."

    second = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_new.jpg")
    assert second.status_code == 200, second.text
    new_data = second.json()["data"]
    assert new_data["verification_status"] == "pending"
    assert new_data["replaces_document_id"] == document_id
    assert new_data["doc_version"] == 2

    # The old, rejected version stays available as history — never deleted — but is no
    # longer the active/current document.
    history = await client.get(f"/api/v1/applications/{application_id}/documents/{product['pan_doc_id']}/history", headers=headers)
    assert history.status_code == 200, history.text
    by_name = {d["file_name"]: d for d in history.json()["data"]}
    assert by_name["pan_old.jpg"]["is_current"] is False
    assert by_name["pan_old.jpg"]["verification_status"] == "rejected"
    assert by_name["pan_new.jpg"]["is_current"] is True
    assert by_name["pan_new.jpg"]["verification_status"] == "pending"

    # Only the current (new) document shows up in the normal list — the rejected one
    # must not appear as a second active document.
    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    current_pan = [d for d in r.json()["data"] if d["document_type_id"] == product["pan_doc_id"]]
    assert len(current_pan) == 1
    assert current_pan[0]["file_name"] == "pan_new.jpg"

    r = await client.patch(f"/api/v1/applications/{application_id}/documents/{new_data['id']}/verify", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "verified"


async def test_staff_can_reject_and_reupload_a_document(client, mock_db, owner_headers, master_data):
    """Section 1D — staff re-upload works through the exact same document model/service
    as customer re-upload; no separate incompatible system."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Staff Reupload")
    customer_headers, application_id = await _start_application(client, product, mobile="9800000202")
    await _upload(client, application_id, product["pan_doc_id"], customer_headers, file_name="pan_v1.jpg")

    assignee = await _create_employee(client, owner_headers, master_data, mobile="9500000202", email="assignee-reupload@example.com")
    await client.post(f"/api/v1/applications/{application_id}/assign", json={"employee_id": assignee["id"]}, headers=owner_headers)
    await _grant_customer_permission(client, owner_headers, assignee["id"], ["view", "edit"], role_name="Reupload Access")
    assignee_headers = await _login(client, "9500000202", "InitialPass1!")

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=assignee_headers)
    document_id = next(d["id"] for d in r.json()["data"] if d["document_type_id"] == product["pan_doc_id"])
    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry scan."}, headers=assignee_headers,
    )
    assert r.status_code == 200, r.text

    replacement = await _upload(client, application_id, product["pan_doc_id"], assignee_headers, file_name="pan_v2.jpg")
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["data"]["verification_status"] == "pending"
    assert replacement.json()["data"]["is_current"] is True


async def test_reject_requires_authorization_same_as_verify(client, mock_db, owner_headers, master_data):
    """Reject must be IDOR/permission-scoped identically to Verify — previously only
    Verify had explicit test coverage for this."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Reject IDOR")
    customer_headers, application_id = await _start_application(client, product, mobile="9800000203")
    r = await _upload(client, application_id, product["pan_doc_id"], customer_headers)
    document_id = r.json()["data"]["id"]

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9500000203", email="bystander-reject@example.com")
    bystander_headers = await _login(client, "9500000203", "InitialPass1!")
    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Not valid."}, headers=bystander_headers,
    )
    assert r.status_code == 403, r.text

    # The customer themselves cannot reject their own document either.
    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Not valid."}, headers=customer_headers,
    )
    assert r.status_code == 403, r.text

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Not valid."}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- Download vs Preview (decision #133)


async def test_download_url_sets_attachment_disposition_distinct_from_preview(client, mock_db, owner_headers, monkeypatch):
    """Preview (`download_url`) stays inline; Download (`attachment_url`) must carry a
    real `Content-Disposition: attachment` so the browser saves the file instead of
    rendering it — the concrete, previously-missing distinction."""
    import app.features.customer.service as customer_service

    captured: list[dict] = []
    real_generate = customer_service.generate_presigned_download_url

    def spy(key, *, expires_in=300, response_content_disposition=None):
        captured.append({"key": key, "disposition": response_content_disposition})
        return real_generate(key, expires_in=expires_in, response_content_disposition=response_content_disposition)

    monkeypatch.setattr(customer_service, "generate_presigned_download_url", spy)

    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Download")
    headers, application_id = await _start_application(client, product, mobile="9800000204")
    await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    assert r.status_code == 200, r.text
    doc = r.json()["data"][0]
    assert doc["download_url"] is not None
    assert doc["attachment_url"] is not None
    assert doc["download_url"] != doc["attachment_url"]

    preview_calls = [c for c in captured if c["disposition"] is None]
    attachment_calls = [c for c in captured if c["disposition"] is not None]
    assert len(preview_calls) == 1
    assert len(attachment_calls) == 1
    assert "attachment" in attachment_calls[0]["disposition"]
    assert "pan.jpg" in attachment_calls[0]["disposition"]


# ---------------------------------------------------------------------- Front & Back upload (decision #133)


async def _seed_product_with_front_back_document(mock_db, *, product_name="Vehicle Loan", front_back_upload=True, multiple_upload=False):
    """A NON-Aadhaar document type (proves front/back is config-driven, not hardcoded to
    any particular document name)."""
    product = LoanProduct(name=product_name)
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    rc_doc = DocumentType(name=f"Vehicle RC-{product_name}")
    rc_doc_id = str((await mock_db["document_types"].insert_one(rc_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    form_def = ApplicationFormDefinition(
        product_category="loan",
        product_id=str(product_id),
        fields=[FormFieldDefinition(key="amount", label="Amount", field_type=FieldType.NUMBER, required=True)],
        required_documents=[
            RequiredDocumentDefinition(document_type_id=rc_doc_id, required=True, front_back_upload=front_back_upload, multiple_upload=multiple_upload)
        ],
        status="active",
    )
    form_def_id = (await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    return {"product_category": "loan", "product_id": str(product_id), "form_definition_id": str(form_def_id), "rc_doc_id": rc_doc_id}


async def test_front_back_upload_persists_and_both_sides_stay_independently_current(client, mock_db, owner_headers):
    product = await _seed_product_with_front_back_document(mock_db, product_name="Vehicle Loan A")
    headers, application_id = await _start_application(client, product, mobile="9800000205")

    front = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_front.jpg", side="front")
    assert front.status_code == 200, front.text
    assert front.json()["data"]["side"] == "front"
    back = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_back.jpg", side="back")
    assert back.status_code == 200, back.text
    assert back.json()["data"]["side"] == "back"

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    docs = [d for d in r.json()["data"] if d["document_type_id"] == product["rc_doc_id"]]
    assert len(docs) == 2
    assert {d["side"] for d in docs} == {"front", "back"}
    assert all(d["is_current"] for d in docs)

    # Re-uploading the front must only supersede the front, never the back.
    new_front = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_front_v2.jpg", side="front")
    assert new_front.status_code == 200, new_front.text
    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    docs = [d for d in r.json()["data"] if d["document_type_id"] == product["rc_doc_id"]]
    assert len(docs) == 2
    front_doc = next(d for d in docs if d["side"] == "front")
    back_doc = next(d for d in docs if d["side"] == "back")
    assert front_doc["file_name"] == "rc_front_v2.jpg"
    assert back_doc["file_name"] == "rc_back.jpg"  # untouched


async def test_front_back_upload_validation_errors(client, mock_db, owner_headers):
    product = await _seed_product_with_front_back_document(mock_db, product_name="Vehicle Loan B")
    headers, application_id = await _start_application(client, product, mobile="9800000206")

    r = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc.jpg")  # no side
    assert r.status_code >= 400, r.text

    r = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc.jpg", side="left")  # invalid side
    assert r.status_code >= 400, r.text

    # A non-front-back document must reject a side.
    plain_product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Side Rejected")
    headers2, application_id2 = await _start_application(client, plain_product, mobile="9800000207")
    r = await _upload(client, application_id2, plain_product["pan_doc_id"], headers2, side="front")
    assert r.status_code >= 400, r.text


async def test_front_back_document_cannot_be_marked_not_available(client, mock_db, owner_headers):
    product = await _seed_product_with_front_back_document(mock_db, product_name="Vehicle Loan C", front_back_upload=False)
    headers, application_id = await _start_application(client, product, mobile="9800000208")
    # Flip to front_back_upload via schema update to reuse the same product without a
    # second document type — required=True either way, so not-available should be
    # blocked regardless of whether the row started front_back.
    r = await client.get(
        f"/api/v1/product-schemas?product_category=loan&product_id={product['product_id']}", headers=owner_headers,
    )
    schema = next(s for s in r.json()["data"] if s["id"] == product["form_definition_id"])
    docs = [{k: v for k, v in d.items() if k not in ("document_type_name", "source", "supports_password")} for d in schema["required_documents"]]
    for d in docs:
        d["front_back_upload"] = True
        d["required"] = False  # not-available is otherwise blocked by `required` first; isolate the front_back check
    r = await client.patch(f"/api/v1/product-schemas/{product['form_definition_id']}", json={"required_documents": docs}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['rc_doc_id']}/not-available", headers=headers)
    assert r.status_code >= 400, r.text


async def test_front_back_and_multiple_upload_mutually_exclusive(client, mock_db, owner_headers):
    product = LoanProduct(name="Vehicle Loan Conflict")
    product_id = (await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    rc_doc = DocumentType(name="Vehicle RC-Conflict")
    rc_doc_id = str((await mock_db["document_types"].insert_one(rc_doc.model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    r = await client.post(
        "/api/v1/product-schemas",
        json={
            "product_category": "loan", "product_id": str(product_id), "status": "active", "fields": [],
            "required_documents": [{"document_type_id": rc_doc_id, "required": True, "front_back_upload": True, "multiple_upload": True}],
        },
        headers=owner_headers,
    )
    assert r.status_code >= 400, r.text


async def test_front_back_completion_requires_both_sides_verified(client, mock_db, owner_headers, master_data):
    """Staff's Document Collection summary (`LeadService._document_completion`) must not
    count a Front & Back requirement as verified until BOTH sides are verified."""
    from app.features.system_settings.models import LeadSource

    product = await _seed_product_with_front_back_document(mock_db, product_name="Vehicle Loan D")
    source_id = str((await mock_db["lead_sources"].insert_one(LeadSource(name="Website").model_dump(by_alias=True, exclude={"id"}))).inserted_id)

    employee = await _create_employee(client, owner_headers, master_data, mobile="9500000209", email="assignee-fb@example.com")
    r = await client.post(
        "/api/v1/leads",
        json={
            "full_name": "Front Back Lead", "mobile": "9800000209", "source_id": source_id, "product_category": "loan",
            "product_id": product["product_id"], "assigned_to": employee["id"],
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    lead_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/leads/{lead_id}/stage", json={"stage": "document_collection"}, headers=owner_headers)
    assert r.status_code == 200, r.text

    headers, application_id = await _start_application(client, product, mobile="9800000210")
    # Link this application to the lead the way the real conversion flow would — directly
    # patch the application's lead_id so the completion summary can resolve it.
    from bson import ObjectId

    await mock_db["applications"].update_one({"_id": ObjectId(application_id)}, {"$set": {"lead_id": lead_id}})

    front = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_front.jpg", side="front")
    await client.patch(f"/api/v1/applications/{application_id}/documents/{front.json()['data']['id']}/verify", headers=owner_headers)

    r = await client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["documents_verified"] == 0  # only front verified so far — not enough

    back = await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_back.jpg", side="back")
    await client.patch(f"/api/v1/applications/{application_id}/documents/{back.json()['data']['id']}/verify", headers=owner_headers)

    r = await client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["documents_verified"] == 1
    assert r.json()["data"]["documents_required"] == 1


async def test_submit_blocked_with_only_one_side_of_front_back_document_uploaded(client, mock_db, owner_headers):
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_with_front_back_document(mock_db, product_name="Vehicle Loan E")
    headers, application_id = await _start_application(client, product, mobile="9800000211")

    await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_front.jpg", side="front")
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code >= 400, r.text

    await _upload(client, application_id, product["rc_doc_id"], headers, file_name="rc_back.jpg", side="back")
    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------- password_protected schema override (decision #133)


async def test_password_protected_override_enables_password_even_when_global_flag_is_false(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan PW Override On")
    r = await client.get(
        f"/api/v1/product-schemas?product_category=loan&product_id={product['product_id']}", headers=owner_headers,
    )
    schema = next(s for s in r.json()["data"] if s["id"] == product["form_definition_id"])
    docs = [{k: v for k, v in d.items() if k not in ("document_type_name", "source", "supports_password")} for d in schema["required_documents"]]
    for d in docs:
        if d["document_type_id"] == product["pan_doc_id"]:
            d["password_protected"] = True
    r = await client.patch(f"/api/v1/product-schemas/{product['form_definition_id']}", json={"required_documents": docs}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(
        "/api/v1/application-form-definitions", params={"product_category": "loan", "product_id": product["product_id"]}, headers=owner_headers,
    )
    pan = next(d for d in r.json()["data"]["required_documents"] if d["document_type_id"] == product["pan_doc_id"])
    assert pan["supports_password"] is True  # PAN's DocumentType itself never set supports_password=True

    headers, application_id = await _start_application(client, product, mobile="9800000212")
    r = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg", password="OverrideSecret1")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["has_password"] is True


async def test_password_protected_override_disables_password_even_when_global_flag_is_true(client, mock_db, owner_headers):
    product = await _seed_product_with_bank_statement(mock_db, product_name="Personal Loan PW Override Off")
    r = await client.get(
        f"/api/v1/product-schemas?product_category=loan&product_id={product['product_id']}", headers=owner_headers,
    )
    schema = next(s for s in r.json()["data"] if s["id"] == product["form_definition_id"])
    docs = [{k: v for k, v in d.items() if k not in ("document_type_name", "source", "supports_password")} for d in schema["required_documents"]]
    for d in docs:
        d["password_protected"] = False
    r = await client.patch(f"/api/v1/product-schemas/{product['form_definition_id']}", json={"required_documents": docs}, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.get(
        "/api/v1/application-form-definitions", params={"product_category": "loan", "product_id": product["product_id"]}, headers=owner_headers,
    )
    bank = r.json()["data"]["required_documents"][0]
    assert bank["supports_password"] is False  # overridden off despite the global DocumentType flag being True

    headers, application_id = await _start_application(client, product, mobile="9800000213")
    r = await _upload(client, application_id, product["bank_doc_id"], headers, file_name="statement.pdf", password="ShouldBeDroppedNow")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["has_password"] is False


async def test_existing_schema_without_new_fields_behaves_exactly_as_before(client, mock_db, owner_headers):
    """Backward compatibility: a schema built with no `front_back_upload`/
    `password_protected` fields at all (every schema that predates this round) must
    behave identically to before — no front/back UI, password support purely inherited
    from the global DocumentType flag."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Compat")
    r = await client.get(
        "/api/v1/application-form-definitions", params={"product_category": "loan", "product_id": product["product_id"]}, headers=owner_headers,
    )
    for d in r.json()["data"]["required_documents"]:
        assert d["front_back_upload"] is False
        assert d["supports_password"] is False

    headers, application_id = await _start_application(client, product, mobile="9800000214")
    r = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["side"] is None


async def test_legacy_rejected_document_missing_the_side_field_entirely_can_still_be_reuploaded(client, mock_db, owner_headers):
    """Real production data predates `side`/`front_back_upload`/`password_protected` —
    a raw Mongo row from before this round has no `side` key in its document AT ALL
    (not even `null`), since it was inserted by code that never knew the field existed.
    Confirms the read path (`ApplicationDocument.model_validate`, defaulting the
    missing key) and the reject-then-reupload flow both work unchanged against that
    exact shape, not just against freshly-written rows that happen to include the new
    fields explicitly."""
    from bson import ObjectId

    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Legacy")
    headers, application_id = await _start_application(client, product, mobile="9800000215")
    first = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_legacy.jpg")
    assert first.status_code == 200, first.text
    document_id = first.json()["data"]["id"]

    # Simulate genuinely pre-existing production data: strip the new field from the raw
    # Mongo document entirely, then reject it exactly as staff would today.
    await mock_db["application_documents"].update_one({"_id": ObjectId(document_id)}, {"$unset": {"side": ""}})
    raw = await mock_db["application_documents"].find_one({"_id": ObjectId(document_id)})
    assert "side" not in raw

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Illegible scan."}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verification_status"] == "rejected"
    assert r.json()["data"]["side"] is None  # reads back with the field defaulted, not an error

    second = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_legacy_v2.jpg")
    assert second.status_code == 200, second.text
    new_data = second.json()["data"]
    assert new_data["is_current"] is True
    assert new_data["verification_status"] == "pending"
    assert new_data["replaces_document_id"] == document_id

    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    current_pan = [d for d in r.json()["data"] if d["document_type_id"] == product["pan_doc_id"]]
    assert len(current_pan) == 1
    assert current_pan[0]["file_name"] == "pan_legacy_v2.jpg"


# ---------------------------------------------------------------------- customer notification on rejection (decision #135)


async def test_rejecting_a_document_creates_a_customer_notification(client, mock_db, owner_headers):
    """Reuses the existing Reminders/Notification engine (RemindersService.notify) —
    the customer must be able to read their own notification via the same self-service
    /notifications endpoints staff already use (widened from staff-only to any
    authenticated user, since the underlying service already scopes strictly to the
    caller's own id)."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify A")
    headers, application_id = await _start_application(client, product, mobile="9800000216")
    upload = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")
    document_id = upload.json()["data"]["id"]

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] == 0

    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject",
        json={"reason": "PAN image is not clear. Please upload a clearer copy."}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] == 1

    r = await client.get("/api/v1/notifications", headers=headers)
    assert r.status_code == 200, r.text
    notifications = r.json()["data"]
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification["notification_type"] == "document_rejected"
    assert notification["category"] == "document"
    assert notification["status"] == "unread"
    assert notification["entity_type"] == "application"
    assert notification["entity_id"] == application_id
    assert "PAN Card" in notification["message"]
    assert "PAN image is not clear. Please upload a clearer copy." in notification["message"]
    # No internal-only staff/verifier identity leaks into the customer-facing payload.
    assert "verified_by" not in notification
    assert "employee" not in str(notification).lower()


async def test_customer_can_mark_the_rejection_notification_read_using_existing_mechanism(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify B")
    headers, application_id = await _start_application(client, product, mobile="9800000217")
    upload = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")
    document_id = upload.json()["data"]["id"]
    await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry."}, headers=owner_headers,
    )

    r = await client.get("/api/v1/notifications", headers=headers)
    notification_id = r.json()["data"][0]["id"]
    assert r.json()["data"][0]["status"] == "unread"

    r = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "read"
    assert r.json()["data"]["read_at"] is not None

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.json()["data"]["unread_count"] == 0

    # Reading the notification never hides the rejection itself from the application's
    # own document view — it must remain visible there independent of notification state.
    r = await client.get(f"/api/v1/applications/{application_id}/documents", headers=headers)
    doc = next(d for d in r.json()["data"] if d["id"] == document_id)
    assert doc["verification_status"] == "rejected"
    assert doc["rejection_reason"] == "Blurry."


async def test_repeated_reject_on_the_same_document_does_not_spam_a_duplicate_notification(client, mock_db, owner_headers):
    """The exact "accidental double-submit" scenario: rejecting the SAME (already-
    rejected) document row again must not create a second notification for what is
    still, functionally, the same rejection event."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify C")
    headers, application_id = await _start_application(client, product, mobile="9800000218")
    upload = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")
    document_id = upload.json()["data"]["id"]

    r1 = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry."}, headers=owner_headers,
    )
    assert r1.status_code == 200, r1.text
    r2 = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry — retry."}, headers=owner_headers,
    )
    assert r2.status_code == 200, r2.text

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.json()["data"]["unread_count"] == 1


async def test_a_new_rejection_after_reupload_creates_a_new_actionable_notification(client, mock_db, owner_headers):
    """A genuinely NEW rejection (on the freshly re-uploaded replacement document, not
    the same row) must fire its own new notification — this is not the same event as
    the first rejection."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify D")
    headers, application_id = await _start_application(client, product, mobile="9800000219")
    first = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_v1.jpg")
    first_id = first.json()["data"]["id"]
    await client.patch(
        f"/api/v1/applications/{application_id}/documents/{first_id}/reject", json={"reason": "Blurry v1."}, headers=owner_headers,
    )

    second = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan_v2.jpg")
    second_id = second.json()["data"]["id"]
    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{second_id}/reject", json={"reason": "Blurry v2 too."}, headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.json()["data"]["unread_count"] == 2
    r = await client.get("/api/v1/notifications?page_size=100", headers=headers)
    messages = [n["message"] for n in r.json()["data"]]
    assert any("Blurry v1." in m for m in messages)
    assert any("Blurry v2 too." in m for m in messages)


async def test_customer_cannot_see_another_customers_rejection_notification(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify E")
    headers_a, application_id = await _start_application(client, product, mobile="9800000220")
    upload = await _upload(client, application_id, product["pan_doc_id"], headers_a, file_name="pan.jpg")
    document_id = upload.json()["data"]["id"]
    await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry."}, headers=owner_headers,
    )

    headers_b, _ = await _start_application(client, product, mobile="9800000221")
    r = await client.get("/api/v1/notifications", headers=headers_b)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []
    r = await client.get("/api/v1/notifications/unread-count", headers=headers_b)
    assert r.json()["data"]["unread_count"] == 0

    # And customer B cannot mark customer A's notification read via a guessed/known id.
    r = await client.get("/api/v1/notifications", headers=headers_a)
    notification_id = r.json()["data"][0]["id"]
    r = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=headers_b)
    assert r.status_code == 404, r.text


async def test_failed_rejection_creates_no_notification(client, mock_db, owner_headers, master_data):
    """A rejection that fails authorization (an unassigned Employee, no permission on
    this application) must never produce a notification — the notification is only
    ever fired after the mutation and its audit log write have both already
    succeeded."""
    product = await _seed_rich_product_and_form(mock_db, product_name="Business Loan Notify F")
    headers, application_id = await _start_application(client, product, mobile="9800000222")
    upload = await _upload(client, application_id, product["pan_doc_id"], headers, file_name="pan.jpg")
    document_id = upload.json()["data"]["id"]

    bystander = await _create_employee(client, owner_headers, master_data, mobile="9500000222", email="bystander-notify@example.com")
    bystander_headers = await _login(client, "9500000222", "InitialPass1!")
    r = await client.patch(
        f"/api/v1/applications/{application_id}/documents/{document_id}/reject", json={"reason": "Blurry."}, headers=bystander_headers,
    )
    assert r.status_code == 403, r.text

    r = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["unread_count"] == 0
