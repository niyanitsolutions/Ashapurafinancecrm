"""Governance round — Master Template / Owner Configuration split, immutable field
keys, the Hide/Show/Required/Optional/relabel/reorder/Add-Custom-Field permission model
(explicitly NOT delete/re-key/re-type a master field), freeze/version/publish lifecycle,
Compare, and Audit History. See `app.features.customer.models` module docstring and
`CustomerService.update_form_definition`'s diff-by-key merge for what this covers.
"""

from app.features.customer.constants import SchemaStatus
from app.features.customer.models import (
    ApplicationFormDefinition,
    FormFieldDefinition,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import DocumentType, LoanProduct


async def _seed_loan_product(mock_db, name="Personal Loan") -> str:
    product = LoanProduct(name=name)
    result = await mock_db["loan_products"].insert_one(product.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_document_type(mock_db, name="PAN Card") -> str:
    doc = DocumentType(name=name)
    result = await mock_db["document_types"].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


async def _seed_governed_schema(mock_db, product_id: str, *, document_type_id: str | None = None, status: str = SchemaStatus.ACTIVE) -> str:
    """A schema that's already been through the master-template apply flow: one
    master-sourced field (`full_name`) and, if a document_type_id is given, one
    master-sourced required document — exactly the shape `apply_product_schema.py`
    produces on first application."""
    fields = [FormFieldDefinition(key="full_name", label="Full Name", field_type="text", required=True, source="master", master_key="full_name")]
    required_documents = []
    if document_type_id:
        required_documents.append(RequiredDocumentDefinition(document_type_id=document_type_id, source="master"))
    form_def = ApplicationFormDefinition(
        product_category="loan", product_id=product_id, fields=fields, required_documents=required_documents, status=status,
    )
    result = await mock_db["application_form_definitions"].insert_one(form_def.model_dump(by_alias=True, exclude={"id"}))
    return str(result.inserted_id)


# --------------------------------------------------------------------------- permission model


async def test_master_field_key_cannot_be_changed(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [{"key": "applicant_full_name", "label": "Full Name", "field_type": "text", "required": True}]},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_master_field_type_cannot_be_changed(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [{"key": "full_name", "label": "Full Name", "field_type": "textarea", "required": True}]},
        headers=owner_headers,
    )
    assert r.status_code == 422, r.text


async def test_master_field_cannot_be_omitted_deleted(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.patch(f"/api/v1/product-schemas/{schema_id}", json={"fields": []}, headers=owner_headers)
    assert r.status_code == 422, r.text


async def test_master_field_can_be_hidden_relabelled_reordered(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={
            "fields": [
                {
                    "key": "full_name", "label": "Applicant Full Name", "field_type": "text", "required": False,
                    "placeholder": "Enter your name", "hidden": True,
                }
            ]
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    field = r.json()["data"]["fields"][0]
    assert field["source"] == "master"
    assert field["master_key"] == "full_name"
    assert field["label"] == "Applicant Full Name"
    assert field["required"] is False
    assert field["placeholder"] == "Enter your name"
    assert field["hidden"] is True


async def test_owner_can_add_and_remove_custom_fields_freely(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={
            "fields": [
                {"key": "full_name", "label": "Full Name", "field_type": "text", "required": True},
                {"key": "referral_code", "label": "Referral Code", "field_type": "text", "required": False},
            ]
        },
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    fields_by_key = {f["key"]: f for f in r.json()["data"]["fields"]}
    assert fields_by_key["referral_code"]["source"] == "custom"

    # Custom fields can be freely removed (only master fields are protected).
    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [{"key": "full_name", "label": "Full Name", "field_type": "text", "required": True}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    assert [f["key"] for f in r.json()["data"]["fields"]] == ["full_name"]


async def test_master_document_cannot_be_removed_but_can_be_hidden(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    document_type_id = await _seed_document_type(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id, document_type_id=document_type_id)

    r = await client.patch(f"/api/v1/product-schemas/{schema_id}", json={"required_documents": []}, headers=owner_headers)
    assert r.status_code == 422, r.text

    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"required_documents": [{"document_type_id": document_type_id, "hidden": True, "required": False}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    doc = r.json()["data"]["required_documents"][0]
    assert doc["source"] == "master"
    assert doc["hidden"] is True
    assert doc["required"] is False


# --------------------------------------------------------------------------- freeze / version / publish


async def test_freeze_locks_further_edits(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)

    r = await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": ["fields_verified"]}, headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_locked"] is True
    assert r.json()["data"]["frozen_at"] is not None

    r = await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={"fields": [{"key": "full_name", "label": "Renamed", "field_type": "text", "required": True}]},
        headers=owner_headers,
    )
    assert r.status_code == 409, r.text

    # Freezing an already-frozen schema is rejected too.
    r = await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": []}, headers=owner_headers)
    assert r.status_code == 409, r.text


async def test_new_version_requires_frozen_and_bypasses_uniqueness_guard(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)

    # Not frozen yet — new-version is rejected.
    r = await client.post(f"/api/v1/product-schemas/{schema_id}/new-version", headers=owner_headers)
    assert r.status_code == 409, r.text

    await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": []}, headers=owner_headers)

    r = await client.post(f"/api/v1/product-schemas/{schema_id}/new-version", headers=owner_headers)
    assert r.status_code == 200, r.text
    draft = r.json()["data"]
    assert draft["status"] == "draft"
    assert draft["is_locked"] is False
    assert draft["schema_version"] == 2
    assert draft["source_schema_version"] == 1
    assert draft["fields"][0]["source"] == "master"
    assert draft["fields"][0]["master_key"] == "full_name"


async def test_publish_archives_previous_active_and_activates_draft(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": []}, headers=owner_headers)
    r = await client.post(f"/api/v1/product-schemas/{schema_id}/new-version", headers=owner_headers)
    draft_id = r.json()["data"]["id"]

    # Publishing an already-active schema (not a draft) is rejected.
    r = await client.post(f"/api/v1/product-schemas/{schema_id}/publish", headers=owner_headers)
    assert r.status_code == 409, r.text

    r = await client.post(f"/api/v1/product-schemas/{draft_id}/publish", headers=owner_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active"

    r = await client.get(f"/api/v1/product-schemas/{schema_id}", headers=owner_headers)
    assert r.json()["data"]["status"] == "archived"
    # The previously-frozen v1 stays frozen even once archived — a permanent record for Compare.
    assert r.json()["data"]["is_locked"] is True


# --------------------------------------------------------------------------- compare / audit


async def test_compare_and_audit_history(client, mock_db, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    await client.patch(
        f"/api/v1/product-schemas/{schema_id}",
        json={
            "fields": [
                {"key": "full_name", "label": "Full Name (Renamed)", "field_type": "text", "required": True},
                {"key": "referral_code", "label": "Referral Code", "field_type": "text", "required": False},
            ]
        },
        headers=owner_headers,
    )
    await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": ["fields_verified"]}, headers=owner_headers)
    new_version = await client.post(f"/api/v1/product-schemas/{schema_id}/new-version", headers=owner_headers)
    draft_id = new_version.json()["data"]["id"]
    # Drop the custom `referral_code` field — omitting the master `full_name` field
    # too would be rejected (see test_master_field_cannot_be_omitted_deleted).
    r = await client.patch(
        f"/api/v1/product-schemas/{draft_id}",
        json={"fields": [{"key": "full_name", "label": "Full Name (Renamed)", "field_type": "text", "required": True}]},
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    await client.post(f"/api/v1/product-schemas/{draft_id}/publish", headers=owner_headers)

    r = await client.get(
        f"/api/v1/product-schemas/compare?product_category=loan&product_id={product_id}&schema_version_a=1&schema_version_b=2",
        headers=owner_headers,
    )
    assert r.status_code == 200, r.text
    compare = r.json()["data"]
    assert [f["key"] for f in compare["removed_fields"]] == ["referral_code"]
    assert compare["added_fields"] == []
    assert compare["modified_fields"] == []

    r = await client.get(f"/api/v1/product-schemas/audit?product_category=loan&product_id={product_id}", headers=owner_headers)
    assert r.status_code == 200, r.text
    events = [e["event_type"] for e in r.json()["data"]]
    assert "schema_field_updated" in events
    assert "schema_frozen" in events
    assert "schema_draft_created" in events
    assert "schema_published" in events


async def test_employee_without_permission_cannot_freeze_or_compare(client, mock_db, employee_headers, owner_headers):
    product_id = await _seed_loan_product(mock_db)
    schema_id = await _seed_governed_schema(mock_db, product_id)
    r = await client.post(f"/api/v1/product-schemas/{schema_id}/freeze", json={"confirmed_checklist": []}, headers=employee_headers)
    assert r.status_code == 403, r.text
    r = await client.get(
        f"/api/v1/product-schemas/compare?product_category=loan&product_id={product_id}&schema_version_a=1&schema_version_b=1",
        headers=employee_headers,
    )
    assert r.status_code == 403, r.text
