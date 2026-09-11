"""Loan — backfill `disbursed_at` for cases force-moved to Disbursed via Staff Override
before the fix in `LoanCaseService.override_move_to_stage`.

Root cause (production bug: "Disbursed tab count shows 9, Disbursed list shows 4"):
`GET /loan-cases/disbursements` (the actual page behind the Disbursed tab) filters on
`loan_details.disbursed_at` within a date range (defaults to "This Month" in the UI) —
report semantics, unrelated to `current_status`. The normal `disburse()` action always
sets `disbursed_at`; a case force-moved to Disbursed via Staff Override, before this fix,
never had it set, so it counted (`get_counts` only checks `current_status`) but could
never appear in the report for ANY date range, and Top Up eligibility scheduling
(`schedule_top_up`, which also requires this field) would fail for it too.

This migration finds every LOAN case currently sitting at `current_status == "disbursed"`
with no `loan_details.disbursed_at` and sets it to that document's `updated_at` — the
timestamp of the move itself (the most recent write to an unmodified-since case),
the closest honest proxy for "when it was actually disbursed" without inventing a new
fact. It never fabricates `disbursed_amount`/`disbursed_reference` (those stay whatever
they already were — "—" in the UI, exactly as a fresh override-disbursed case behaves
after the code fix).

**Only `application_workflows` rows with `case_type == "loan"` are touched — a handful of
existing Disbursed cases at most. Insurance is never read or written.** Idempotent: a row
that already has `disbursed_at` is skipped; re-running is a no-op.

Run from repo root: python scripts/migrate_backfill_disbursed_at_for_override_cases.py
Run from backend/:  python ../scripts/migrate_backfill_disbursed_at_for_override_cases.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database


async def _backfill(db) -> None:
    workflows = db["application_workflows"]
    candidates = await workflows.find(
        {
            "case_type": "loan",
            "current_status": "disbursed",
            "is_deleted": False,
            "$or": [{"loan_details.disbursed_at": None}, {"loan_details.disbursed_at": {"$exists": False}}],
        }
    ).to_list(length=100_000)

    backfilled = 0
    for row in candidates:
        as_of = row.get("updated_at") or row.get("created_at")
        await workflows.update_one({"_id": row["_id"]}, {"$set": {"loan_details.disbursed_at": as_of}})
        backfilled += 1
        print(f"  {row.get('case_code', row['_id'])}: disbursed_at backfilled -> {as_of}")

    print(f"\napplication_workflows (loan, disbursed): backfilled {backfilled} of {len(candidates)} candidate row(s). Insurance untouched.")
    if backfilled and any(not (r.get("loan_details") or {}).get("disbursed_amount") for r in candidates):
        print(
            "Note: some backfilled cases have no disbursed_amount/disbursed_reference "
            "(never collected by the override action that moved them) — the UI shows "
            "\"—\" for those, exactly like a fresh override-disbursed case after the code fix."
        )


async def main() -> None:
    db = get_database()
    print(f"Connected to database: {db.name!r}")
    await _backfill(db)


if __name__ == "__main__":
    asyncio.run(main())
