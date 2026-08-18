"""One-time backfill for the Employee Permission Matrix redesign's Customers row.

`scripts/seed.py`'s `seed_ui_navigation_nav_items()` originally seeded the "customers"
and "applications" `nav_items` rows with no `required_module`/`required_resource`/
`required_action` at all (mirroring the routes' old `_staff: StaffDep`-only gate). The
Employee Permission Matrix redesign later put `CustomerViewDep` —
`require_permission("customer", "customers", "view")` — in front of both routes
(`GET /customers`, `GET /applications`), but the nav catalog was never updated to
match, so on any database seeded before that redesign, the "Customers" sidebar link
stays visible to every Owner/Employee regardless of grant even though the underlying
API now 403s them without one.

`seed.py` itself can't fix an already-provisioned document — its upsert uses
`$setOnInsert`, which only writes on first insert and is a no-op against a row that
already exists. This script explicitly backfills the two already-seeded rows in place.

Idempotent: safe to run twice. A `nav_items` row that already carries the gate (either
because this script already ran, or because `seed.py` inserted it fresh post-fix) is
left untouched. Touches only `required_module`/`required_resource`/`required_action` on
these two specific rows — no other nav_items field, no RolePermission grant, no
Permission catalog entry.

Run from backend/:  python ../scripts/migrate_gate_customer_nav_items.py
Run from repo root: python scripts/migrate_gate_customer_nav_items.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database  # noqa: E402
from app.features.access_control.constants import PermissionAction  # noqa: E402
from app.features.dashboard.repository import NavItemRepository  # noqa: E402

_GATE = {"required_module": "customer", "required_resource": "customers", "required_action": PermissionAction.VIEW}


async def main() -> None:
    db = get_database()
    nav_items = NavItemRepository(db)

    print(f"Connected to database: {db.name!r}")

    updated = 0
    skipped_already_gated = 0
    skipped_missing = 0

    for key in ("customers", "applications"):
        item = await nav_items.find_by_key(key)
        if item is None:
            print(f"nav_items[{key!r}] not found — nothing to backfill (run seed_ui_navigation_nav_items first if this is a fresh database).")
            skipped_missing += 1
            continue
        if item.required_module == _GATE["required_module"] and item.required_resource == _GATE["required_resource"] and item.required_action == _GATE["required_action"]:
            print(f"nav_items[{key!r}] already gated - skipping.")
            skipped_already_gated += 1
            continue
        await nav_items.update(item.require_id(), dict(_GATE))
        print(f"nav_items[{key!r}] gated to customer:customers:view.")
        updated += 1

    print(f"Done. updated={updated} skipped_already_gated={skipped_already_gated} skipped_missing={skipped_missing}")


if __name__ == "__main__":
    asyncio.run(main())
