"""Production redesign — Loan Management workflow & complete application view.

`scripts/seed.py::seed_workflow_definitions` writes with `$setOnInsert`, which only
applies to a brand-new document — editing the Loan row tuples there (adding `REJECTED`
to five statuses' `allowed_next_statuses`, and populating `allowed_previous_statuses`
for the new "Move Back" feature) has ZERO effect on an already-seeded database. This
script `$set`-updates both fields on every existing Loan `WorkflowDefinition` row that
changed. Safe to re-run (idempotent `$set`); never touches Insurance rows or any
`ApplicationWorkflow`/case document.

Run from repo root: python scripts/migrate_loan_workflow_transitions.py
Run from backend/:  python ../scripts/migrate_loan_workflow_transitions.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.workflow_engine.constants import ON_HOLD_STATUS, LoanStatus

# Must match scripts/seed.py's current loan_rows `allowed_next_statuses` for these
# statuses exactly, or the live database and the seed source of truth for a fresh
# install would silently diverge.
_UPDATED_ALLOWED_NEXT: dict[str, list[str]] = {
    LoanStatus.NEW_CUSTOMER: [LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED],
    LoanStatus.ADDITIONAL_DOCUMENTS: [LoanStatus.RV_OV_REF, LoanStatus.REJECTED, ON_HOLD_STATUS],
    LoanStatus.RV_OV_REF: [LoanStatus.ESIGN_NACH_KYC, LoanStatus.REJECTED, ON_HOLD_STATUS],
    LoanStatus.ESIGN_NACH_KYC: [LoanStatus.FINAL_EVALUATION, LoanStatus.REJECTED, ON_HOLD_STATUS],
    LoanStatus.SEND_FOR_DISBURSEMENT: [LoanStatus.DISBURSED, LoanStatus.REJECTED, ON_HOLD_STATUS],
}

# New this round: "Move Back" — must match scripts/seed.py's `loan_allowed_previous`.
_UPDATED_ALLOWED_PREVIOUS: dict[str, list[str]] = {
    LoanStatus.CREDIT_EVALUATION: [LoanStatus.NEW_CUSTOMER],
    LoanStatus.OFFER_ACCEPTANCE: [LoanStatus.CREDIT_EVALUATION],
    LoanStatus.ADDITIONAL_DOCUMENTS: [LoanStatus.OFFER_ACCEPTANCE],
    LoanStatus.RV_OV_REF: [LoanStatus.ADDITIONAL_DOCUMENTS],
    LoanStatus.ESIGN_NACH_KYC: [LoanStatus.RV_OV_REF],
    LoanStatus.FINAL_EVALUATION: [LoanStatus.ESIGN_NACH_KYC],
    LoanStatus.SEND_FOR_DISBURSEMENT: [LoanStatus.FINAL_EVALUATION],
}


async def main() -> None:
    db = get_database()
    definitions = db["workflow_definitions"]

    print(f"Connected to database: {db.name!r}")

    print("\n== Updating allowed_next_statuses (adding Reject where missing) ==")
    for status, allowed_next in _UPDATED_ALLOWED_NEXT.items():
        existing = await definitions.find_one({"case_type": "loan", "status": status})
        if existing is None:
            print(f"  SKIP {status!r}: no existing row found (a fresh install will get it correctly from scripts/seed.py instead).")
            continue
        result = await definitions.update_one({"case_type": "loan", "status": status}, {"$set": {"allowed_next_statuses": allowed_next}})
        print(f"  {status!r}: allowed_next_statuses -> {allowed_next} (matched={result.matched_count}, modified={result.modified_count})")

    print("\n== Updating allowed_previous_statuses (new 'Move Back' feature) ==")
    statuses = set(_UPDATED_ALLOWED_NEXT) | set(_UPDATED_ALLOWED_PREVIOUS)
    for status in sorted(statuses):
        allowed_previous = _UPDATED_ALLOWED_PREVIOUS.get(status, [])
        existing = await definitions.find_one({"case_type": "loan", "status": status})
        if existing is None:
            print(f"  SKIP {status!r}: no existing row found (a fresh install will get it correctly from scripts/seed.py instead).")
            continue
        result = await definitions.update_one({"case_type": "loan", "status": status}, {"$set": {"allowed_previous_statuses": allowed_previous}})
        print(f"  {status!r}: allowed_previous_statuses -> {allowed_previous} (matched={result.matched_count}, modified={result.modified_count})")

    print("\nDone. No case documents were created, deleted, or destructively modified.")


if __name__ == "__main__":
    asyncio.run(main())
