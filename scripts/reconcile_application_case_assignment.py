"""One-time reconciliation: fix `Application.assigned_to` / `ApplicationWorkflow.assigned_to`
divergence that could occur before `CustomerService.assign_application` and
`LoanCaseService`/`InsuranceCaseService.assign_case` were made to keep both sides in sync.

Application and its Loan/Insurance Case each carried an independently-editable
`assigned_to` field. A Case only ever inherited `Application.assigned_to` once, at case
creation; reassigning either side afterward never propagated to the other. This is why
Loan Management could show a case as assigned to an employee while the Customer
Applications list showed the very same underlying application as Unassigned. The code
fix keeps both sides in sync going forward — this script repairs data that already
diverged before that fix shipped. It does not need to run more than once in the normal
case, but is safe to re-run (idempotent): a second run finds nothing left to reconcile
except any conflicts logged (and not resolved) by the first run.

For every existing Case, compares it against its Application:
  - If exactly one side is null, copies the other side's (non-null) value across. This
    is the unambiguous, safe case, and is exactly the reported bug's shape: a case
    reassigned after creation while the application side was never touched by the old
    code (or vice versa).
  - If BOTH sides are set but disagree, this is a genuine conflict between two
    legitimately-set values — printed as `CONFLICT (manual review needed)` and NEVER
    auto-resolved. No production data is silently overwritten. A human must decide which
    value is correct and re-trigger either `POST /applications/{id}/assign` or
    `POST /loan-cases|insurance-cases/{id}/assign` — both endpoints now propagate to the
    other side automatically, so a single explicit reassignment resolves the conflict on
    both records at once.

Run from backend/:  python ../scripts/reconcile_application_case_assignment.py
Run from repo root: python scripts/reconcile_application_case_assignment.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.customer.repository import ApplicationRepository
from app.features.workflow_engine.repository import ApplicationWorkflowRepository


async def main() -> None:
    db = get_database()
    applications = ApplicationRepository(db)
    workflows = ApplicationWorkflowRepository(db)

    print(f"Connected to database: {db.name!r}")

    all_cases = await workflows.find_many({}, limit=100000)
    print(f"Found {len(all_cases)} case(s) to check.")

    synced = 0
    conflicts = 0
    missing_application = 0

    for case in all_cases:
        application = await applications.find_by_id(case.application_id)
        if application is None:
            missing_application += 1
            print(f"  WARNING: case_id={case.require_id()!r} case_code={case.case_code!r} has no matching application_id={case.application_id!r} — skipped.")
            continue

        if application.assigned_to == case.assigned_to:
            continue

        if application.assigned_to is None and case.assigned_to is not None:
            await applications.update(application.require_id(), {"assigned_to": case.assigned_to})
            synced += 1
            print(
                f"  synced application_id={application.require_id()!r} application_code={application.application_code!r} "
                f"<- case_code={case.case_code!r} assigned_to={case.assigned_to!r}"
            )
        elif case.assigned_to is None and application.assigned_to is not None:
            await workflows.update(case.require_id(), {"assigned_to": application.assigned_to})
            synced += 1
            print(
                f"  synced case_id={case.require_id()!r} case_code={case.case_code!r} "
                f"<- application_code={application.application_code!r} assigned_to={application.assigned_to!r}"
            )
        else:
            conflicts += 1
            print(
                f"  CONFLICT (manual review needed): application_code={application.application_code!r} assigned_to={application.assigned_to!r}"
                f"  vs  case_code={case.case_code!r} assigned_to={case.assigned_to!r}"
            )

    print(
        f"\nDone. cases_checked={len(all_cases)}  synced={synced}  "
        f"conflicts_needing_manual_review={conflicts}  cases_missing_application={missing_application}"
    )


if __name__ == "__main__":
    asyncio.run(main())
