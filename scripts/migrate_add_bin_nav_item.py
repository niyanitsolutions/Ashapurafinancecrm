"""Add the Owner-only "Bin" nav item to an already-seeded database.

`scripts/seed.py::seed_bin_nav_item` upserts with `$setOnInsert`, so a fresh install
gets it — an existing database needs this one-line upsert. Idempotent.

Run from repo root: python scripts/migrate_add_bin_nav_item.py
Run from backend/:  python ../scripts/migrate_add_bin_nav_item.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database


async def main() -> None:
    db = get_database()
    print(f"Connected to database: {db.name!r}")
    result = await db["nav_items"].update_one(
        {"key": "bin"},
        {
            "$setOnInsert": {
                "key": "bin", "label": "Bin", "route": "/bin", "icon": None, "order": 95,
                "owner_only": True, "required_module": None, "required_resource": None, "required_action": None,
                "is_deleted": False, "status": "active", "version": 1,
            }
        },
        upsert=True,
    )
    print(f"nav_items 'bin': upserted={result.upserted_id is not None} matched={result.matched_count}")


if __name__ == "__main__":
    asyncio.run(main())
