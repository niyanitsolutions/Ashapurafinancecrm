"""Insurance Policy Leads redesign — Phase 2: category-aware Product Schemas + the
"New Schema" creatable-products picker + the Customer Portal category-first read.

Loan schemas must be completely unaffected (no insurance_category_id, one-step product
list).
"""

API = "/api/v1"


async def _insurance_category(client, owner_headers, name="Health Insurance") -> str:
    r = await client.post(f"{API}/insurance-categories", json={"name": name}, headers=owner_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _insurance_product(client, owner_headers, category_id, name="Family Health Plus") -> str:
    r = await client.post(
        f"{API}/insurance-products", json={"name": name, "category_id": category_id}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _loan_product(mock_db, name="Personal Loan") -> str:
    from app.features.system_settings.models import LoanProduct

    result = await mock_db["loan_products"].insert_one(LoanProduct(name=name).model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


def _schema_payload(product_category, product_id, status="draft"):
    return {"product_category": product_category, "product_id": product_id, "fields": [], "required_documents": [], "status": status}


# ---------------------------------------------------------------- category on the schema


async def test_insurance_schema_stores_and_returns_category(client, mock_db, owner_headers):
    category_id = await _insurance_category(client, owner_headers)
    product_id = await _insurance_product(client, owner_headers, category_id)

    r = await client.post(f"{API}/product-schemas", json=_schema_payload("insurance", product_id), headers=owner_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["insurance_category_id"] == category_id
    assert data["insurance_category_name"] == "Health Insurance"

    # Carried through a new version.
    schema_id = data["id"]
    await client.post(f"{API}/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": []}, headers=owner_headers)
    r = await client.post(f"{API}/product-schemas/{schema_id}/new-version", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["insurance_category_id"] == category_id


async def test_loan_schema_has_no_insurance_category(client, mock_db, owner_headers):
    product_id = await _loan_product(mock_db)
    r = await client.post(f"{API}/product-schemas", json=_schema_payload("loan", product_id), headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["insurance_category_id"] is None
    assert r.json()["data"]["insurance_category_name"] is None


async def test_insurance_schema_rejected_when_product_has_no_category(client, mock_db, owner_headers):
    result = await mock_db["insurance_products"].insert_one({"name": "Orphan", "status": "active", "is_deleted": False, "version": 1})
    r = await client.post(f"{API}/product-schemas", json=_schema_payload("insurance", str(result.inserted_id)), headers=owner_headers)
    assert r.status_code == 422


async def test_insurance_schema_rejected_when_category_inactive(client, mock_db, owner_headers):
    category_id = await _insurance_category(client, owner_headers, "Life Insurance")
    product_id = await _insurance_product(client, owner_headers, category_id, "Term Life")
    # A category can't be deactivated while it has an active product, so deactivate the
    # product first, then the category.
    await client.patch(f"{API}/insurance-products/{product_id}/deactivate", headers=owner_headers)
    r = await client.patch(f"{API}/insurance-categories/{category_id}/deactivate", headers=owner_headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"{API}/product-schemas", json=_schema_payload("insurance", product_id), headers=owner_headers)
    assert r.status_code == 409


# ---------------------------------------------------------------- creatable products


async def test_creatable_products_excludes_products_that_have_a_schema(client, mock_db, owner_headers):
    category_id = await _insurance_category(client, owner_headers)
    p1 = await _insurance_product(client, owner_headers, category_id, "Family Health Plus")
    p2 = await _insurance_product(client, owner_headers, category_id, "Senior Citizen Health")

    r = await client.get(f"{API}/product-schemas/creatable-products?product_category=insurance", headers=owner_headers)
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["data"]}
    assert ids == {p1, p2}
    assert all(row["category_name"] == "Health Insurance" for row in r.json()["data"])

    await client.post(f"{API}/product-schemas", json=_schema_payload("insurance", p1), headers=owner_headers)
    r = await client.get(f"{API}/product-schemas/creatable-products?product_category=insurance", headers=owner_headers)
    assert {row["id"] for row in r.json()["data"]} == {p2}


async def test_creatable_products_loan(client, mock_db, owner_headers):
    product_id = await _loan_product(mock_db)
    r = await client.get(f"{API}/product-schemas/creatable-products?product_category=loan", headers=owner_headers)
    assert r.status_code == 200
    assert [row["id"] for row in r.json()["data"]] == [product_id]
    assert r.json()["data"][0]["category_id"] is None


async def test_creatable_products_requires_permission(client, mock_db, employee_headers):
    r = await client.get(f"{API}/product-schemas/creatable-products?product_category=insurance", headers=employee_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------- customer portal category-first


async def test_portal_category_first_insurance_flow(client, mock_db, owner_headers):
    from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
    from app.security.password import hash_password

    health_id = await _insurance_category(client, owner_headers, "Health Insurance")
    life_id = await _insurance_category(client, owner_headers, "Life Insurance")
    await _insurance_product(client, owner_headers, health_id, "Family Health Plus")
    await _insurance_product(client, owner_headers, life_id, "Term Life")

    user = User(mobile="9800000009", role="customer", status=ACCOUNT_STATUS_ACTIVE, password_hash=hash_password("CustPass1!"))
    await mock_db["users"].insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    login = await client.post("/api/v1/auth/login", json={"mobile": "9800000009", "password": "CustPass1!"})
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    cats = await client.get("/api/v1/portal-insurance-categories", headers=headers)
    assert cats.status_code == 200, cats.text
    assert {c["name"] for c in cats.json()["data"]} == {"Health Insurance", "Life Insurance"}

    scoped = await client.get(f"/api/v1/portal-products?category=insurance&insurance_category_id={health_id}", headers=headers)
    assert [p["name"] for p in scoped.json()["data"]] == ["Family Health Plus"]

    # Loan stays flat (one step, no category param needed).
    loan = await client.get("/api/v1/portal-products?category=loan", headers=headers)
    assert loan.status_code == 200
