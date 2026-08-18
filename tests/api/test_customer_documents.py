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


async def _upload(client, application_id, doc_type_id, headers, *, file_name="doc.pdf", content_type="application/pdf"):
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url",
        json={"document_type_id": doc_type_id, "file_name": file_name, "content_type": content_type}, headers=headers,
    )
    if upload.status_code != 200:
        return upload
    s3_key = upload.json()["data"]["s3_key"]
    return await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": doc_type_id, "file_name": file_name, "s3_key": s3_key, "content_type": content_type}, headers=headers,
    )


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


async def test_marking_a_required_document_not_available_is_rejected(client, mock_db, owner_headers):
    product = await _seed_rich_product_and_form(mock_db)
    headers, application_id = await _start_application(client, product, mobile="9800000003")

    r = await client.post(f"/api/v1/applications/{application_id}/documents/{product['pan_doc_id']}/not-available", headers=headers)
    assert r.status_code == 403, r.text


async def test_owner_flipping_optional_to_required_after_not_available_blocks_submit(client, mock_db, owner_headers):
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
    assert r.status_code == 403, r.text  # now required — can't be waived
    r = await client.post(f"/api/v1/applications/{application_id2}/submit", json={}, headers=headers2)
    assert r.status_code >= 400, r.text  # still missing — blocked


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
