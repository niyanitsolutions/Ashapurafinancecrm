"""One-time backfill for the Leads workflow redesign, Phase 1 (decision 125 in
docs/decisions/DECISIONS.md).

`Lead.stage` is a new field (default `"fresh"` in the Pydantic model) backing the
redesigned Fresh Leads / My Leads / Document Collection / Rejected / Assigned tabs. A
Lead created before this field existed reads back with Pydantic's default (`"fresh"`)
even if it's actually `assigned_to`-set — which would silently misplace an
already-assigned lead into the Fresh Leads tab instead of My Leads. This script sets the
correct `stage` explicitly on every pre-existing Lead, based on whether `assigned_to`
was already set at the time this ran:

  - `assigned_to` is set  -> `stage = "assigned"` (My Leads). `assigned_by`/`assigned_at`
    are left null — there's no reliable historical actor/timestamp to recover for a
    pre-existing assignment (the "assigned" LeadActivity, if one exists, only ever
    recorded `employee_id`, not who performed the assignment as a top-level Lead field
    until this redesign). This is a one-time, accepted gap, not a bug.
  - `assigned_to` is null -> `stage = "fresh"`.

Also ensures the seeded `leads:leads` Permission catalog entry includes the new
"reject" action — `scripts/seed.py` uses `$setOnInsert`, so re-running seed against an
already-provisioned database does NOT retroactively add a new action to an existing
catalog document; this script does that explicitly via `$addToSet`.

Idempotent: only ever sets `stage` on a document that doesn't already have one (i.e.
`{"stage": {"$exists": False}}`), and `$addToSet` is a no-op if "reject" is already
present — safe to run twice.

**Must run once before deploying the Phase 1 backend** (new list/count endpoints filter
by `stage`) — running it after would leave every pre-existing lead absent from all 5 tabs
until this script executes.

Run from backend/:  python ../scripts/migrate_backfill_lead_stage.py
Run from repo root: python scripts/migrate_backfill_lead_stage.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.leads.constants import LeadStage


async def main() -> None:
    db = get_database()
    leads = db["leads"]

    print(f"Connected to database: {db.name!r}")

    no_stage_filter = {"stage": {"$exists": False}}

    assigned_result = await leads.update_many(
        {**no_stage_filter, "assigned_to": {"$ne": None}}, {"$set": {"stage": LeadStage.ASSIGNED}}
    )
    fresh_result = await leads.update_many({**no_stage_filter, "assigned_to": None}, {"$set": {"stage": LeadStage.FRESH}})

    permission_result = await db["permissions"].update_one(
        {"module": "leads", "resource": "leads"}, {"$addToSet": {"actions": "reject"}}
    )

    print(
        f"\nDone. leads_backfilled_to_assigned={assigned_result.modified_count} "
        f"leads_backfilled_to_fresh={fresh_result.modified_count} "
        f"leads_permission_reject_action_added={permission_result.modified_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
