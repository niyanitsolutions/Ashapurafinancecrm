"""Final Phase — regression coverage for Phase 1's Owner-facing Product Schema CRUD
(`/product-schemas`), which shipped with zero pytest coverage across Phases 1-3.1. Also
covers the input-validation fix made during the Final Phase review: a malformed
`field_type`/`operator`/`format` must be rejected as a clean 422 at the request-body
boundary, not bubble up as an unhandled 500 from deep inside the service layer.
"""

from app.features.system_settings.models import LoanProduct


async def _seed_loan_product(mock_db, name="Personal Loan") -> str:
    product = LoanProduct(name=name)
    result = await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


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
