"""Add the `rejected -> re_eligible` edge to the Loan pipeline's workflow definition.

`scripts/seed.py::seed_workflow_definitions` now seeds the loan `rejected` row with
`allowed_next_statuses=["re_eligible"]`, but it upserts with `$setOnInsert`, so editing
that tuple has ZERO effect on an already-seeded database. This script `$set`-updates the
one existing row so the `auto_transition_re_eligible_cases` worker job (which moves a
scheduled rejected case to `re_eligible` on its date) can actually perform that
transition — `WorkflowEngine.assert_transition_allowed` reads this list.

Safe to re-run (idempotent `$set`). Never touches Insurance rows or any case document.
Same shape/pattern as `scripts/migrate_loan_workflow_transitions.py`.

Run from repo root: python scripts/migrate_rejected_re_eligible_transition.py
Run from backend/:  python ../scripts/migrate_rejected_re_eligible_transition.py
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

    existing = await definitions.find_one({"case_type": "loan", "status": LoanStatus.REJECTED})
    if existing is None:
        print("  SKIP: no loan 'rejected' workflow_definitions row (a fresh install gets it correctly from scripts/seed.py).")
        return

    allowed_next = sorted({*(existing.get("allowed_next_statuses") or []), LoanStatus.RE_ELIGIBLE})
    result = await definitions.update_one(
        {"case_type": "loan", "status": LoanStatus.REJECTED},
        {"$set": {"allowed_next_statuses": allowed_next}},
    )
    print(f"  loan:rejected allowed_next_statuses -> {allowed_next} (matched={result.matched_count}, modified={result.modified_count})")
    print("\nDone. No case documents were created, deleted, or destructively modified.")


if __name__ == "__main__":
    asyncio.run(main())
