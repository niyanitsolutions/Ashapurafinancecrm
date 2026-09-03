"""Insurance Policy Leads redesign — Phase 1: Insurance Category master + Product link.

Introduces the `insurance_categories` collection and a `category_id` on every
`insurance_products` row. This script:

  1. Ensures the two baseline categories exist ("Health Insurance", "Life Insurance") —
     idempotent upsert on `name`, never overwriting an existing row.
  2. Backfills `category_id` on existing insurance products that don't have one yet:
       - "Health" (case-insensitive) -> Health Insurance
       - everything else            -> Life Insurance   (the safe catch-all; an Owner
                                        can reassign afterwards in Settings)
  3. Ensures the collection indexes (`insurance_categories.name` unique,
     `insurance_products.category_id`).

**Safety-first, never destructive**: no product or category row is ever deleted or
renamed. A product that already has a `category_id` is left untouched. Safe to run
repeatedly.

Run from repo root: python scripts/migrate_add_insurance_categories.py
Run from backend/:  python ../scripts/migrate_add_insurance_categories.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.system_settings.models import InsuranceCategory

_BASELINE_CATEGORIES = ("Health Insurance", "Life Insurance")


async def main() -> None:
    db = get_database()
    categories = db["insurance_categories"]
    products = db["insurance_products"]

    print(f"Connected to database: {db.name!r}")

    await categories.create_index("name", unique=True)
    await products.create_index("category_id")

    category_id_by_name: dict[str, str] = {}
    for name in _BASELINE_CATEGORIES:
        payload = InsuranceCategory(name=name).model_dump(by_alias=True, exclude={"id"})
        await categories.update_one({"name": name}, {"$setOnInsert": payload}, upsert=True)
        row = await categories.find_one({"name": name}, {"_id": 1})
        assert row is not None
        category_id_by_name[name] = str(row["_id"])
    print(f"Baseline categories ensured: {category_id_by_name}")

    health_id = category_id_by_name["Health Insurance"]
    life_id = category_id_by_name["Life Insurance"]

    unassigned = await products.find(
        {"$or": [{"category_id": None}, {"category_id": {"$exists": False}}], "is_deleted": False}
    ).to_list(length=1000)

    if not unassigned:
        print("No insurance products need a category backfill. Done.")
        return

    updated = 0
    for product in unassigned:
        name = str(product.get("name", ""))
        target = health_id if "health" in name.lower() else life_id
        await products.update_one({"_id": product["_id"]}, {"$set": {"category_id": target}})
        target_name = "Health Insurance" if target == health_id else "Life Insurance"
        print(f"  {name!r} -> {target_name}")
        updated += 1

    print(f"\nBackfilled category_id on {updated} insurance product(s). Nothing was deleted or renamed.")


if __name__ == "__main__":
    asyncio.run(main())
