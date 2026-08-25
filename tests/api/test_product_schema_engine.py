"""Final Phase — regression coverage for Phase 1's Owner-facing Product Schema CRUD
(`/product-schemas`), which shipped with zero pytest coverage across Phases 1-3.1. Also
covers the input-validation fix made during the Final Phase review: a malformed
`field_type`/`operator`/`format` must be rejected as a clean 422 at the request-body
boundary, not bubble up as an unhandled 500 from deep inside the service layer.

Production fix — "Gender must be a dropdown in ALL Product Schemas": the standardized
Gender field (`key == "gender"`) is coerced to a static Male/Female/Other Select by
`FormFieldDefinition`'s own model_validator (see customer/models.py), regardless of what
field_type/options a create/update payload supplies — this is the ONE place that
enforcement lives, so it applies to every product (existing or future) with zero
per-product code. `test_customer.py`'s `_seed_product_and_form`/`_signup_via_otp`/
`_create_employee` are reused for the end-to-end application-submission tests.
"""

from app.features.system_settings.models import LoanProduct
from test_customer import _seed_product_and_form, _seed_workflow_definitions, _signup_via_otp


async def _seed_loan_product(mock_db, name="Personal Loan") -> str:
    product = LoanProduct(name=name)
    result = await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


def _gender_field(field_type="text", options=None):
    """A deliberately WRONG configuration (free-text, no options) — Staff misconfiguring
    it this way (or a pre-existing free-text Gender field from before this fix) is
    exactly the bug being tested; the backend must self-correct it regardless."""
    payload = {"key": "gender", "label": "Gender", "field_type": field_type, "required": True}
    if options is not None:
        payload["options"] = options
    return payload


async def test_create_and_fetch_product_schema(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {
        "product_category": "loan",
        "product_id": product_id,
        "fields": [{"key": "loan_amount", "label": "Loan Amount", "field_type": "number", "required": True, "section": "Basic Information"}],
        "required_documents": [],
        "status": "active",
    }
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    created = r.json()["data"]
    assert created["status"] == "active"
    assert created["version"] == 1
    assert created["fields"][0]["key"] == "loan_amount"

    r = await client.get("/api/v1/product-schemas", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert any(s["id"] == created["id"] for s in r.json()["data"])

    r = await client.get(f"/api/v1/product-schemas/{created['id']}", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["id"] == created["id"]


async def test_cannot_create_duplicate_schema_for_same_product(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {"product_category": "loan", "product_id": product_id, "fields": [], "required_documents": []}
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 409, r.text


async def test_update_increments_version_and_edits_fields(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {"product_category": "loan", "product_id": product_id, "fields": [], "required_documents": [], "status": "draft"}
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    schema_id = r.json()["data"]["id"]
    assert r.json()["data"]["version"] == 1

    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [{"key": "full_name", "label": "Full Name", "field_type": "text", "required": True}], "status": "active"},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()["data"]
    assert updated["version"] == 2
    assert updated["status"] == "active"
    assert updated["fields"][0]["key"] == "full_name"


async def test_draft_schema_is_not_served_by_the_shared_by_product_lookup(client, mock_db, owner_headers, employee_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {"product_category": "loan", "product_id": product_id, "fields": [], "required_documents": [], "status": "draft"}
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text

    # The shared read every portal's dynamic form uses (Employee Create Lead, Referral
    # Add Lead, Customer Application) must not see a draft-only schema.
    r = await client.get(f"/api/v1/application-form-definitions?product_category=loan&product_id={product_id}", headers=employee_headers)
    assert r.status_code == 422, r.text  # "No application form is configured for this product yet."


async def test_malformed_field_type_is_rejected_as_clean_422_not_500(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {
        "product_category": "loan", "product_id": product_id, "required_documents": [],
        "fields": [{"key": "x", "label": "X", "field_type": "not-a-real-type"}],
    }
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_malformed_condition_operator_is_rejected_as_clean_422(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    payload = {
        "product_category": "loan", "product_id": product_id, "required_documents": [],
        "fields": [
            {"key": "a", "label": "A", "field_type": "text"},
            {"key": "b", "label": "B", "field_type": "text", "visible_when": {"field_key": "a", "operator": "not-a-real-operator", "value": "x"}},
        ],
    }
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_employee_without_permission_cannot_manage_product_schemas(client, mock_db, employee_headers):
    r = await client.get("/api/v1/product-schemas", headers=employee_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------- Gender standardization (production fix)


async def test_gender_field_is_always_a_male_female_other_dropdown_on_create(client, mock_db, owner_headers):
    """Test 5/8 — Staff configuring Gender as free text (or omitting options entirely)
    gets a real Select with exactly Male/Female/Other back anyway; the schema/field-
    definition level enforcement, not a per-product frontend hack."""
    product_id = await _seed_loan_product(mock_db, "Personal Loan")
    payload = {
        "product_category": "loan", "product_id": product_id, "required_documents": [], "status": "active",
        "fields": [_gender_field(field_type="text")],
    }
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    assert r.status_code == 200, r.text
    field = r.json()["data"]["fields"][0]
    assert field["field_type"] == "select"
    assert field["options"] == ["Male", "Female", "Other"]
    assert field["options_source"] == "static"


async def test_gender_dropdown_behavior_is_generic_across_multiple_products(client, mock_db, owner_headers):
    """Test 6 — not fixed for one product only. Two entirely separate products (their
    own LoanProduct + ApplicationFormDefinition, no shared code path) both get the
    identical Gender dropdown with zero product-specific handling."""
    for product_name in ("Business Loan", "Home Loan", "Vehicle Loan"):
        product_id = await _seed_loan_product(mock_db, product_name)
        payload = {
            "product_category": "loan", "product_id": product_id, "required_documents": [], "status": "active",
            "fields": [_gender_field(field_type="text")],
        }
        r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
        assert r.status_code == 200, r.text
        field = r.json()["data"]["fields"][0]
        assert field["field_type"] == "select", f"{product_name} did not get the Gender dropdown"
        assert field["options"] == ["Male", "Female", "Other"], f"{product_name} has wrong Gender options"


async def test_gender_field_configuration_persists_across_update_and_reload(client, mock_db, owner_headers):
    """Test 7 — save, then reload (a fresh GET, a genuinely separate request) must show
    the identical Dropdown/Male/Female/Other configuration, not something computed only
    at create time."""
    product_id = await _seed_loan_product(mock_db)
    payload = {
        "product_category": "loan", "product_id": product_id, "required_documents": [], "status": "draft",
        "fields": [_gender_field(field_type="text")],
    }
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    schema_id = r.json()["data"]["id"]

    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [_gender_field(field_type="text"), {"key": "extra", "label": "Extra Field", "field_type": "text", "required": False}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/product-schemas/{schema_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    gender = next(f for f in r.json()["data"]["fields"] if f["key"] == "gender")
    assert gender["field_type"] == "select"
    assert gender["options"] == ["Male", "Female", "Other"]


async def test_gender_field_type_and_options_cannot_be_overridden_via_update(client, mock_db, owner_headers):
    """An Owner explicitly trying to turn Gender back into free text, or change its
    options, is silently overridden rather than allowed through — the standardized field
    stays standardized regardless of what a request supplies."""
    product_id = await _seed_loan_product(mock_db)
    payload = {"product_category": "loan", "product_id": product_id, "required_documents": [], "status": "active", "fields": [_gender_field()]}
    r = await client.post("/api/v1/product-schemas", json=payload, headers=owner_headers)
    schema_id = r.json()["data"]["id"]

    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [_gender_field(field_type="text", options=["X", "Y"])]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    field = r.json()["data"]["fields"][0]
    assert field["field_type"] == "select"
    assert field["options"] == ["Male", "Female", "Other"]


async def test_application_submission_rejects_invalid_gender_value(client, mock_db, owner_headers):
    """Test 10 — the frontend dropdown alone is not sufficient: an arbitrary value
    outside Male/Female/Other must be rejected server-side when the field is the
    standardized Select-type Gender field."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    schema_id = str((await mock_db["application_form_definitions"].find_one({"product_id": product["product_id"]}))["_id"])
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={
            "fields": [
                {"key": "loan_amount", "label": "Loan Amount", "field_type": "number", "required": True},
                _gender_field(field_type="text"),
            ]
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9611122001"})
    customer_headers = await _signup_via_otp(client, "9611122001", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Gender Test Customer"}, headers=customer_headers)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]
    await client.patch(
        f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000, "gender": "unknown-value"}}, headers=customer_headers
    )
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"},
        headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 422, r.text
    assert "Gender" in r.json()["error"]["message"]

    # Test 9 — a canonical value is accepted, persists, and submission succeeds.
    # (form_data is a full-replace on PATCH, matching how the real form state is sent —
    # so every field is resupplied here, not only the one being corrected.)
    r = await client.patch(
        f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000, "gender": "Female"}}, headers=customer_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["form_data"]["gender"] == "Female"

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text


async def test_application_submission_accepts_legacy_gender_value(client, mock_db, owner_headers):
    """Test 11 — legacy compatibility. "Male"/"Female"/"Other" is exactly the value
    already stored on every pre-existing application (see the one product that already
    had this right, `scripts/seed_product_schemas.py`'s Business Loan schema) — the new
    canonical Select uses the identical strings as both value and label, so no legacy
    value is silently destroyed or rejected."""
    await _seed_workflow_definitions(mock_db)
    product = await _seed_product_and_form(mock_db)
    schema_id = str((await mock_db["application_form_definitions"].find_one({"product_id": product["product_id"]}))["_id"])
    await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={
            "fields": [
                {"key": "loan_amount", "label": "Loan Amount", "field_type": "number", "required": True},
                _gender_field(field_type="text"),
            ]
        },
        headers=owner_headers,
    )

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": "9611122002"})
    customer_headers = await _signup_via_otp(client, "9611122002", r.json()["data"]["dev_otp"])
    await client.post("/api/v1/customers/me", json={"full_name": "Legacy Gender Customer"}, headers=customer_headers)
    r = await client.post(
        "/api/v1/applications", json={"product_category": product["product_category"], "product_id": product["product_id"]}, headers=customer_headers
    )
    application_id = r.json()["data"]["id"]
    await client.patch(
        f"/api/v1/applications/{application_id}", json={"form_data": {"loan_amount": 500000, "gender": "Male"}}, headers=customer_headers
    )
    upload = await client.post(
        f"/api/v1/applications/{application_id}/documents/upload-url", json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf"},
        headers=customer_headers,
    )
    s3_key = upload.json()["data"]["s3_key"]
    await client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_type_id": product["document_type_id"], "file_name": "pan.pdf", "s3_key": s3_key}, headers=customer_headers,
    )

    r = await client.post(f"/api/v1/applications/{application_id}/submit", json={}, headers=customer_headers)
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/applications/{application_id}", headers=customer_headers)
    assert r.json()["data"]["form_data"]["gender"] == "Male"
