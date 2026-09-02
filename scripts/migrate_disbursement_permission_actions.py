"""Backfill `approve`/`reject` onto the Loan & Insurance case permission-catalog rows.

`scripts/seed.py::seed_permission_catalog` now seeds `loan_management:applications` and
`insurance_management:applications` with
`actions=[view, edit, approve, reject, assign]` — but it upserts with `$setOnInsert`, so
a database first seeded before `approve`/`reject` were added to that list still carries
the old `actions` value. `PermissionEngine.has_permission` rejects any action that isn't
in `permission.actions`, so on such a database an Owner *cannot even grant* the
`approve` action to an Employee role — which is exactly why "Send For Disbursement →
Mark Disbursed" (gated on `approve`, or now `approve`-or-`edit`) is invisible/forbidden
for every Employee.

This script `$addToSet`s `approve` and `reject` onto both existing rows. It never
removes an action, never touches any other permission row, and never touches a
`role_permissions` grant — so no employee gains any access from running it; it only
makes the action *grantable*. Idempotent: a second run is a true no-op.

Safe against unknown production state: skips-and-logs rather than raising.

Run from repo root: python scripts/migrate_disbursement_permission_actions.py
Run from backend/:  python ../scripts/migrate_disbursement_permission_actions.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database

_TARGETS = (
    ("loan_management", "applications"),
    ("insurance_management", "applications"),
)
_ACTIONS_TO_ENSURE = ["approve", "reject"]


async def main() -> None:
    db = get_database()
    permissions = db["permissions"]

    print(f"Connected to database: {db.name!r}")

    for module, resource in _TARGETS:
        existing = await permissions.find_one({"module": module, "resource": resource, "is_deleted": False})
        if existing is None:
            print(f"  SKIP {module}:{resource}: no permission row found (a fresh install gets it correctly from scripts/seed.py).")
            continue
        before = list(existing.get("actions") or [])
        result = await permissions.update_one(
            {"module": module, "resource": resource, "is_deleted": False},
            {"$addToSet": {"actions": {"$each": _ACTIONS_TO_ENSURE}}},
        )
        after_doc = await permissions.find_one({"module": module, "resource": resource, "is_deleted": False})
        after = list((after_doc or {}).get("actions") or [])
        print(f"  {module}:{resource}: actions {before} -> {after} (matched={result.matched_count}, modified={result.modified_count})")

    print("\nDone. No role grants were changed; the actions are now grantable via Roles & Permissions.")


if __name__ == "__main__":
    asyncio.run(main())
