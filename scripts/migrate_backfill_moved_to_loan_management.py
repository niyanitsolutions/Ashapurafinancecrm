"""One-time backfill for the Loan Management eligibility-gate fix (decision #130).

`ApplicationWorkflow.moved_to_loan_management_at` is a new field. Before this fix, a Loan
Case (case_type="loan") was fully visible and actionable in Loan Management the instant
the linked Application was submitted — completely independent of whether the Lead's
separate "Move to Loan Management" action was ever used, and regardless of whether
documents were actually staff-verified (only "uploaded" was ever checked). Staff have
therefore been legitimately working existing production cases all along, regardless of
that decoupled Lead-stage bookkeeping field.

Retroactively gating on the Lead's stage would make currently-in-progress production
cases vanish from the Loan Management list — a regression, not a fix. This script instead
grandfathers every existing case: it sets `moved_to_loan_management_at = created_at` on
every `application_workflows` row with `case_type="loan"` that doesn't already have the
field set. Only NEW cases created after this deploys are subject to the real gate —
staying hidden until the Lead's "Move to Loan Management" action explicitly marks them
(or, for a lead-less/self-registered application with no Document Collection pipeline to
gate through, immediately at creation — see `LoanCaseService._create_case_for_application`).

Idempotent: only touches rows matching
`{"case_type": "loan", "moved_to_loan_management_at": {"$exists": False}}` — a second run
is a no-op. Never deletes or destructively rewrites a case; no Insurance row is touched.

**Must run once before the new backend code is deployed** — the new list/count/detail
gate is live the moment the new code ships, and running this script afterward would hide
every pre-existing loan case from staff until it executes.

Run from repo root: python scripts/migrate_backfill_moved_to_loan_management.py
Run from backend/:  python ../scripts/migrate_backfill_moved_to_loan_management.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database


async def main() -> None:
    db = get_database()
    workflows = db["application_workflows"]

    print(f"Connected to database: {db.name!r}")

    unset_filter = {"case_type": "loan", "moved_to_loan_management_at": {"$exists": False}}
    cursor = workflows.find(unset_filter, {"created_at": 1})
    updated = 0
    async for doc in cursor:
        result = await workflows.update_one({"_id": doc["_id"]}, {"$set": {"moved_to_loan_management_at": doc["created_at"]}})
        updated += result.modified_count

    print(f"\nDone. loan_cases_backfilled={updated}")
    print("No case was deleted or destructively rewritten; every backfilled row keeps its own original created_at as the grandfathered move timestamp.")


if __name__ == "__main__":
    asyncio.run(main())
