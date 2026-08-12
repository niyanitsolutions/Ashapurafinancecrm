"""One-product-at-a-time schema application — companion to `seed_product_schemas.py`.

`seed_product_schemas.py`'s own upsert is `$setOnInsert`-only by design (so a later
in-app Owner edit is never clobbered by re-running it) — but that means it silently
no-ops for any product whose `application_form_definitions` row already existed before
the rich, spec-matching content in that file was authored. Several products in this
environment are in exactly that state: a real, running `loan_products`/
`insurance_products` row paired with an old, generic placeholder schema (or no schema at
all) — never the spec content.

This script applies ONE named product's already-authored content (reused verbatim from
`seed_product_schemas.py`'s own `LOAN_PRODUCTS`/`LIFE_INSURANCE_PRODUCTS`/
`HEALTH_INSURANCE_PRODUCTS` catalogs — nothing is redefined here), matching the "review
this product, approve it, freeze it, move to the next" workflow: run this once per
product, per phase, never touching any product not named on the command line.

Governance round (see `app.features.customer.models` module docstring): every run also
writes/refreshes a `FormTemplateMaster` — the client's official spec, never editable
through any API — and, the *first* time a product is applied, clones it into the real
Owner Configuration (`application_form_definitions`) with every field/document tagged
`source="master"` so the new Owner-permission model (hide/relabel/reorder allowed;
delete/re-key/re-type forbidden) actually has something to protect. If the Owner
Configuration already carries at least one `source="master"` field (i.e. this product
was already applied once under this governance model), re-running this script refreshes
only the Master Template — an Owner's later customization through the real editor UI is
never silently overwritten by a template refresh.

Usage (same convention as `docs/RUN_LOCAL.md`'s `python ../scripts/seed.py`):
    cd backend && ../.venv/Scripts/python.exe ../scripts/apply_product_schema.py "Personal Loan"
"""

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from seed_product_schemas import (
    HEALTH_INSURANCE_PRODUCTS,
    LIFE_INSURANCE_PRODUCTS,
    LOAN_PRODUCTS,
    _upsert_by_name,
)

from app.config.database import get_database
from app.features.customer.constants import SchemaStatus
from app.features.customer.models import (
    ApplicationFormDefinition,
    FormFieldDefinition,
    FormTemplateMaster,
    RequiredDocumentDefinition,
)
from app.features.system_settings.models import DocumentType, InsuranceProduct, LoanProduct

_ALL_CATALOGS: list[tuple[str, list[dict[str, Any]]]] = [
    ("loan", LOAN_PRODUCTS),
    ("insurance", LIFE_INSURANCE_PRODUCTS),
    ("insurance", HEALTH_INSURANCE_PRODUCTS),
]


def _find_entry(product_name: str) -> tuple[str, dict[str, Any]]:
    for category, catalog in _ALL_CATALOGS:
        for entry in catalog:
            if entry["name"].lower() == product_name.lower():
                return category, entry
    available = ", ".join(entry["name"] for _cat, catalog in _ALL_CATALOGS for entry in catalog)
    raise SystemExit(f"'{product_name}' has no authored content in seed_product_schemas.py.\nAvailable: {available}")


async def apply_product_schema(product_name: str) -> None:
    db: AsyncIOMotorDatabase[Any] = get_database()
    category, entry = _find_entry(product_name)
    products_collection = db["loan_products"] if category == "loan" else db["insurance_products"]
    document_types = db["document_types"]
    form_templates = db["form_template_masters"]
    form_definitions = db["application_form_definitions"]

    if category == "loan":
        product_id = await _upsert_by_name(products_collection, entry["name"], lambda: LoanProduct(name=entry["name"]))
    else:
        product_id = await _upsert_by_name(
            products_collection, entry["name"], lambda: InsuranceProduct(name=entry["name"], description=entry.get("description"))
        )

    doc_type_ids: dict[str, str] = {}

    async def doc_type_id(name: str) -> str:
        if name not in doc_type_ids:
            doc_type_ids[name] = await _upsert_by_name(document_types, name, lambda: DocumentType(name=name))
        return doc_type_ids[name]

    master_fields: list[FormFieldDefinition] = []
    for section_name, section_fields in entry["sections"]:
        for field in section_fields:
            master_fields.append(field.model_copy(update={"section": section_name}))

    master_documents: list[RequiredDocumentDefinition] = []
    for group_name, docs in entry["document_groups"]:
        for doc_name, note in docs:
            resolved_id = await doc_type_id(doc_name)
            master_documents.append(RequiredDocumentDefinition(document_type_id=resolved_id, section=group_name, note=note))

    # 1. Master Template — always refreshed, never touched by any API endpoint.
    existing_master = await form_templates.find_one({"product_category": category, "product_id": product_id})
    master_doc = FormTemplateMaster(product_category=category, product_id=product_id, fields=master_fields, required_documents=master_documents)
    master_payload = master_doc.model_dump(by_alias=True, exclude={"id", "created_at", "created_by", "version"})
    master_payload["updated_at"] = datetime.now(UTC)
    if existing_master:
        await form_templates.update_one({"_id": existing_master["_id"]}, {"$set": master_payload, "$inc": {"version": 1}})
    else:
        await form_templates.insert_one(master_doc.model_dump(by_alias=True, exclude={"id"}))

    # 2. Owner Configuration — full apply only the first time; a config that already
    # carries master-tagged fields is presumed to have gone through real Owner review
    # since, so it's left alone (only the Master Template above is refreshed).
    existing_config = await form_definitions.find_one({"product_category": category, "product_id": product_id})
    already_migrated = existing_config is not None and any(f.get("source") == "master" for f in existing_config.get("fields", []))

    if already_migrated:
        print(f"[{category}] {entry['name']}: Master Template refreshed; Owner Configuration already governed — left untouched.")
        return

    fields = [f.model_copy(update={"source": "master", "master_key": f.key}) for f in master_fields]
    required_documents = [d.model_copy(update={"source": "master"}) for d in master_documents]
    definition = ApplicationFormDefinition(
        product_category=category, product_id=product_id, fields=fields, required_documents=required_documents, status=SchemaStatus.ACTIVE,
    )
    payload = definition.model_dump(by_alias=True, exclude={"id", "created_at", "created_by", "version"})
    payload["updated_at"] = datetime.now(UTC)

    if existing_config:
        await form_definitions.update_one({"_id": existing_config["_id"]}, {"$set": payload, "$inc": {"version": 1}})
        action = "updated"
    else:
        await form_definitions.insert_one(definition.model_dump(by_alias=True, exclude={"id"}))
        action = "created"

    print(f"[{category}] {entry['name']}: {action} — {len(fields)} field(s) across {len(entry['sections'])} section(s), "
          f"{len(required_documents)} required document(s) across {len(entry['document_groups'])} group(s), all tagged source=master.")
    if existing_config:
        print(f"  previous: {len(existing_config.get('fields', []))} field(s), {len(existing_config.get('required_documents', []))} document(s)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python ../scripts/apply_product_schema.py "<Product Name>"')
    asyncio.run(apply_product_schema(sys.argv[1]))
