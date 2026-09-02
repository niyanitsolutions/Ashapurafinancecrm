"""Re-Eligible Case Management enhancement — workflow-definition change.

`scripts/seed.py::seed_workflow_definitions` upserts with `$setOnInsert`, so editing the
loan `re_eligible` row's `allowed_next_statuses` has ZERO effect on an already-seeded
database. This script MERGES `new_customer` into the loan `re_eligible` row's
`allowed_next_statuses` (keeping whatever the live row already carries — `credit_evaluation`,
`rejected`, `on_hold`), so a re-eligible case's "Move Case To" dropdown can offer the
restart-safe destinations.

Safe to re-run (idempotent). Never touches Insurance rows or any case document. Same
shape as `scripts/migrate_rejected_re_eligible_transition.py`.

Run from repo root: python scripts/migrate_re_eligible_restart_transitions.py
Run from backend/:  python ../scripts/migrate_re_eligible_restart_transitions.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.workflow_engine.constants import LoanStatus


async def main() -> None:
    db = get_database()
    definitions = db["workflow_definitions"]
    print(f"Connected to database: {db.name!r}")

    row = await definitions.find_one({"case_type": "loan", "status": LoanStatus.RE_ELIGIBLE})
    if row is None:
        print("  SKIP: no loan 're_eligible' row (a fresh install gets it from scripts/seed.py).")
        return

    merged = list(row.get("allowed_next_statuses") or [])
    if LoanStatus.NEW_CUSTOMER not in merged:
        merged.append(LoanStatus.NEW_CUSTOMER)
    result = await definitions.update_one(
        {"case_type": "loan", "status": LoanStatus.RE_ELIGIBLE}, {"$set": {"allowed_next_statuses": merged}}
    )
    print(f"  re_eligible: allowed_next_statuses -> {merged} (matched={result.matched_count}, modified={result.modified_count})")
    print("\nDone. No case documents were created, deleted, or destructively modified.")


if __name__ == "__main__":
    asyncio.run(main())
