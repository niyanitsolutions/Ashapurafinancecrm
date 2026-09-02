"""Re-Eligible Case Management enhancement — workflow-definition changes.

`scripts/seed.py::seed_workflow_definitions` upserts with `$setOnInsert`, so editing the
loan rows has ZERO effect on an already-seeded database. This script:

1. Upserts the loan `documents_pending` ("Document Collection") `WorkflowDefinition` row
   if it doesn't exist (with `on_hold` appended, matching how the seed loop builds it).
2. `$set`-updates `allowed_next_statuses` on the existing loan `new_customer` and
   `re_eligible` rows, MERGING the new restart-safe targets into whatever the live row
   already has (so `on_hold`, added by earlier rounds, is never dropped).

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
from app.features.workflow_engine.constants import ON_HOLD_STATUS, LoanAuditEvent, LoanStatus
from app.features.workflow_engine.models import WorkflowDefinition

_ADD_TARGETS: dict[str, list[str]] = {
    LoanStatus.NEW_CUSTOMER: [LoanStatus.DOCUMENTS_PENDING, LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED],
    LoanStatus.RE_ELIGIBLE: [
        LoanStatus.NEW_CUSTOMER, LoanStatus.DOCUMENTS_PENDING, LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED,
    ],
}


async def main() -> None:
    db = get_database()
    definitions = db["workflow_definitions"]
    print(f"Connected to database: {db.name!r}")

    # 1. Document Collection row.
    existing_dc = await definitions.find_one({"case_type": "loan", "status": LoanStatus.DOCUMENTS_PENDING})
    if existing_dc is None:
        definition = WorkflowDefinition(
            case_type="loan", status=LoanStatus.DOCUMENTS_PENDING, label="Document Collection", sequence=12,
            allowed_next_statuses=[LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED, ON_HOLD_STATUS],
            required_permission="loan_management:applications:edit", customer_editable=False, employee_editable=True,
            audit_event=LoanAuditEvent.DOCUMENTS_REQUESTED, notification_trigger_key="loan_case.documents_requested",
        )
        await definitions.insert_one(definition.model_dump(by_alias=True, exclude={"id"}))
        print("  inserted loan 'documents_pending' (Document Collection) workflow definition")
    else:
        print("  loan 'documents_pending' row already exists — left as-is")

    # 2. Merge new restart targets into new_customer / re_eligible.
    for status, add in _ADD_TARGETS.items():
        row = await definitions.find_one({"case_type": "loan", "status": status})
        if row is None:
            print(f"  SKIP {status!r}: no existing row (a fresh install gets it from scripts/seed.py).")
            continue
        merged = list(row.get("allowed_next_statuses") or [])
        for target in add:
            if target not in merged:
                merged.append(target)
        result = await definitions.update_one(
            {"case_type": "loan", "status": status}, {"$set": {"allowed_next_statuses": merged}}
        )
        print(f"  {status!r}: allowed_next_statuses -> {merged} (matched={result.matched_count}, modified={result.modified_count})")

    print("\nDone. No case documents were created, deleted, or destructively modified.")


if __name__ == "__main__":
    asyncio.run(main())
