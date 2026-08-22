"""Production bug fix — duplicate lead prevention (see docs/decisions/DECISIONS.md).

`LeadService.create_lead` now blocks creating a second lead for a mobile number that
already has an ACTIVE (non-rejected) lead — enforced at the application layer. This
script adds the matching database-level safety net: a **partial** unique index on
`leads.mobile`, scoped to `{"rejected_at": None}` (every non-rejected lead — regardless
of stage: fresh/assigned/document_collection/loan_management — has `rejected_at=None`;
only a rejected lead ever has it set to a real timestamp). This guards against a race
between two near-simultaneous creates for the same mobile slipping past the
application-level check; it deliberately does NOT enforce global uniqueness on `mobile`
across ALL leads — a mobile may freely repeat across multiple *rejected* leads, and
across one rejected + one active lead, matching the business rule exactly.

**Safety-first, never destructive**: this script NEVER deletes, merges, or modifies any
existing Lead. It first INSPECTS for pre-existing violations (more than one non-rejected
lead already sharing a mobile) and, if any are found, only REPORTS them — it does not
attempt to create the index in that case (MongoDB would refuse anyway: a unique index
cannot be built over data that already violates it). Re-run this script after a human
has manually resolved any reported conflicts (e.g. rejecting the true duplicate, or
confirming both are legitimately distinct customers who happen to share a number and
handling that as a data-quality exception outside this script's scope) — it is safe to
run repeatedly; creating an index that already exists with the same options is a no-op.

Run from repo root: python scripts/migrate_add_lead_mobile_unique_index.py
Run from backend/:  python ../scripts/migrate_add_lead_mobile_unique_index.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pymongo.errors import DuplicateKeyError, OperationFailure

from app.config.database import get_database


async def main() -> None:
    db = get_database()
    leads = db["leads"]

    print(f"Connected to database: {db.name!r}")

    # Inspect first — every non-rejected lead has rejected_at=None; group by mobile
    # among exactly those and look for any group with more than one member.
    pipeline = [
        {"$match": {"rejected_at": None, "is_deleted": False}},
        {"$group": {"_id": "$mobile", "count": {"$sum": 1}, "lead_codes": {"$push": "$lead_code"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    conflicts = await leads.aggregate(pipeline).to_list(length=1000)

    if conflicts:
        print(f"\nFound {len(conflicts)} mobile number(s) with more than one ACTIVE (non-rejected) lead:\n")
        for c in conflicts:
            print(f"  mobile={c['_id']!r}  leads={c['lead_codes']}")
        print(
            "\nNo index was created. Nothing was deleted or modified. Resolve these "
            "manually (e.g. reject the genuine duplicate via the existing Reject action) "
            "and re-run this script to finish adding the database-level constraint."
        )
        return

    print("\nNo conflicting active-duplicate mobiles found. Creating the partial unique index...")
    try:
        await leads.create_index(
            "mobile", unique=True, partialFilterExpression={"rejected_at": None}, name="mobile_unique_active_only"
        )
        print("Done. leads.mobile is now unique among non-rejected leads.")
    except (DuplicateKeyError, OperationFailure) as exc:
        # Defensive — the inspection above should already have caught this, but a
        # concurrent write between inspection and index creation is (remotely) possible.
        print(f"\nIndex creation failed: {exc}. No data was modified. Re-run this script after investigating.")


if __name__ == "__main__":
    asyncio.run(main())
