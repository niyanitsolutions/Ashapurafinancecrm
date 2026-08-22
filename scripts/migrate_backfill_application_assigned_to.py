"""One-time backfill: seed `Application.assigned_to` from a matching Lead's own
`assigned_to` for pre-existing Applications left unassigned by the "Relationship
Manager: Not yet assigned" bug.

Before that fix, `CustomerService._create_application` never copied `Lead.assigned_to`
onto the new `Application` it created — so any customer whose Lead staff had already
assigned before the customer created their Application started that Application (and
therefore the customer portal's own RM display, which reads `Application.assigned_to`)
unassigned, even though a real staff assignment existed on the originating Lead.

This finds every Application with `assigned_to=None` and a `customer_id`, looks up any
Lead sharing that `customer_id` and the same `product_category`/`product_id`, and — only
if that Lead has its own `assigned_to` set — copies it onto the Application, exactly the
way the fixed code now does automatically at creation time for new Applications.

Deliberately does NOT touch an Application that already has a Loan/Insurance Case (its
`assigned_to` is a live mirror of the case's own assignment, kept in sync by
`assign_application`/`assign_case` — this script must never override that with a
possibly-stale Lead value) or an Application whose `assigned_to` is already set.

Idempotent: safe to run twice — the second run finds nothing left to backfill.

Run from backend/:  python ../scripts/migrate_backfill_application_assigned_to.py
Run from repo root: python scripts/migrate_backfill_application_assigned_to.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.customer.repository import ApplicationRepository
from app.features.leads.repository import LeadRepository
from app.features.workflow_engine.repository import ApplicationWorkflowRepository


async def main() -> None:
    db = get_database()
    applications = ApplicationRepository(db)
    leads = LeadRepository(db)
    workflows = ApplicationWorkflowRepository(db)

    print(f"Connected to database: {db.name!r}")

    unassigned = await applications.find_many({"assigned_to": None, "customer_id": {"$ne": None}}, limit=100000)
    print(f"Found {len(unassigned)} unassigned application(s) with a customer_id to check.")

    backfilled = 0
    for application in unassigned:
        # Never override a Case's own live-mirrored assignment — only a still-unassigned
        # Application (no Case exists yet, or the Case is also unassigned) is a candidate.
        case = await workflows.find_by_application_id(application.require_id())
        if case is not None and case.assigned_to is not None:
            continue

        candidate = None
        for lead in await leads.find_many(
            {"customer_id": application.customer_id, "product_category": application.product_category, "product_id": application.product_id},
            limit=5,
        ):
            if lead.assigned_to:
                candidate = lead
                break
        if candidate is None:
            continue

        await applications.update(application.require_id(), {"assigned_to": candidate.assigned_to})
        backfilled += 1
        print(
            f"  application_id={application.require_id()!r} application_code={application.application_code!r} "
            f"<- assigned_to={candidate.assigned_to!r} (from lead_id={candidate.require_id()!r})"
        )

    print(f"\nDone. applications_checked={len(unassigned)}  applications_backfilled={backfilled}")


if __name__ == "__main__":
    asyncio.run(main())
