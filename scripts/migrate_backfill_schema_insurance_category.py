"""Insurance Policy Leads redesign — Phase 2: backfill `insurance_category_id` on
insurance Product Schemas.

`ApplicationFormDefinition` gained an `insurance_category_id` field (denormalized from
the product's `category_id`) so category-scoped reads need no product lookup. This
script sets it on every insurance `application_form_definitions` row (all statuses —
draft/active/archived) that doesn't have one yet, copying the value from the linked
`insurance_products.category_id`.

**Never destructive**: only fills a missing `insurance_category_id`; a schema that
already has one, and every loan schema, is left untouched. Safe to run repeatedly.
Run before/after the Phase 1 category migration in any order.

Run from repo root: python scripts/migrate_backfill_schema_insurance_category.py
Run from backend/:  python ../scripts/migrate_backfill_schema_insurance_category.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database


async def main() -> None:
    db = get_database()
    form_defs = db["application_form_definitions"]
    products = db["insurance_products"]

    print(f"Connected to database: {db.name!r}")

    pending = await form_defs.find(
        {
            "product_category": "insurance",
            "is_deleted": False,
            "$or": [{"insurance_category_id": None}, {"insurance_category_id": {"$exists": False}}],
        }
    ).to_list(length=2000)

    if not pending:
        print("No insurance product schemas need an insurance_category_id backfill. Done.")
        return

    updated = 0
    skipped = 0
    for schema in pending:
        product = await products.find_one({"_id": _as_object_id(schema.get("product_id"))}, {"category_id": 1, "name": 1})
        category_id = product.get("category_id") if product else None
        if not category_id:
            print(f"  SKIP schema {schema['_id']} — product has no category_id (run migrate_add_insurance_categories.py first)")
            skipped += 1
            continue
        await form_defs.update_one({"_id": schema["_id"]}, {"$set": {"insurance_category_id": category_id}})
        print(f"  schema {schema['_id']} ({product.get('name', '?')}) -> category_id {category_id}")
        updated += 1

    print(f"\nBackfilled insurance_category_id on {updated} schema(s); {skipped} skipped. Nothing was deleted.")


def _as_object_id(value: object) -> object:
    """`product_id` is stored as a string on the schema but `_id` on the product is an
    ObjectId. Convert when possible; fall back to the raw value for a mongomock/plain-id DB."""
    try:
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            return ObjectId(str(value))
        except InvalidId:
            return value
    except ImportError:  # pragma: no cover - bson always present with motor
        return value


if __name__ == "__main__":
    asyncio.run(main())
