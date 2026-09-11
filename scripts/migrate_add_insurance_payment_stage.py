"""Insurance "Policy Leads" — add the Payment stage (production add-on, 2026-09-11).

Inserts a real, backend-enforced `payment` stage between Policy Login and Policy Issued:

    fresh_lead -> policy_document -> policy_login -> payment -> policy_issued

Same caveat as every prior insurance workflow-definition change in this codebase
(`migrate_redesign_insurance_pipeline.py`, `migrate_recruitment_stage_split.py`):
`scripts/seed.py` only inserts a workflow-definition row with `$setOnInsert`, so an
already-seeded database's existing `policy_login` row keeps its OLD
`allowed_next_statuses` (`[policy_issued, rejected]`) forever unless explicitly rewritten.
This script:

  1. Inserts (or re-asserts) the new `payment` `workflow_definitions` row
     (case_type="insurance"), sequence 4, allowed_next=[policy_issued, rejected],
     allowed_previous=[policy_login].
  2. Rewrites the existing `policy_login` row's `allowed_next_statuses` to
     `[payment, rejected]` (was `[policy_issued, rejected]`).
  3. Re-sequences `policy_issued` (5), `re_eligible` (6), `rejected` (7) so the tab order
     stays correct — sequence numbers only, no other field on those three rows changes.

**Only `workflow_definitions` rows for `case_type == "insurance"` are touched. No
`application_workflows` case document is modified — an existing case already sitting at
`policy_login` simply now goes through Payment before Policy Issued, exactly like the
production spec requires; nothing is silently moved for it. Loan is never read or
written.** Idempotent: safe to re-run — every write is a `$set` to the same target
values.

Run from repo root: python scripts/migrate_add_insurance_payment_stage.py
Run from backend/:  python ../scripts/migrate_add_insurance_payment_stage.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.workflow_engine.constants import (
    ON_HOLD_STATUS,
    InsuranceAuditEvent,
    InsuranceStatus,
)

# Same `BaseDocument` lifecycle shape `migrate_redesign_insurance_pipeline.py` uses for an
# upserted row — every lookup filters on `is_deleted`, so an upsert that omits these
# fields would insert an invisible row.
_BASE_DOCUMENT_FIELDS: dict[str, object] = {
    "is_deleted": False, "deleted_at": None, "deleted_by": None,
    "version": 1, "created_by": None, "updated_by": None,
}


async def _migrate(db) -> None:
    definitions = db["workflow_definitions"]

    payment_payload = {
        **_BASE_DOCUMENT_FIELDS,
        "case_type": "insurance", "status": InsuranceStatus.PAYMENT, "label": "Payment", "sequence": 4,
        "allowed_next_statuses": [InsuranceStatus.POLICY_ISSUED, InsuranceStatus.REJECTED, ON_HOLD_STATUS],
        "allowed_previous_statuses": [InsuranceStatus.POLICY_LOGIN],
        "required_permission": "insurance_management:applications:edit", "customer_editable": False,
        "employee_editable": True, "audit_event": InsuranceAuditEvent.PAYMENT_STARTED,
        "notification_trigger_key": "insurance_case.payment_started", "reminder_trigger_key": None,
    }
    await definitions.update_one(
        {"case_type": "insurance", "status": InsuranceStatus.PAYMENT}, {"$set": payment_payload}, upsert=True
    )

    login_result = await definitions.update_one(
        {"case_type": "insurance", "status": InsuranceStatus.POLICY_LOGIN},
        {"$set": {"allowed_next_statuses": [InsuranceStatus.PAYMENT, InsuranceStatus.REJECTED, ON_HOLD_STATUS]}},
    )

    for status, sequence in (
        (InsuranceStatus.POLICY_ISSUED, 5), (InsuranceStatus.RE_ELIGIBLE, 6), (InsuranceStatus.REJECTED, 7),
    ):
        await definitions.update_one({"case_type": "insurance", "status": status}, {"$set": {"sequence": sequence}})

    print(
        f"workflow_definitions: upserted 'payment' row; policy_login rewritten "
        f"(matched {login_result.matched_count}); re-sequenced policy_issued/re_eligible/rejected. "
        "No application_workflows case document was touched. Loan untouched."
    )


async def main() -> None:
    db = get_database()
    print(f"Connected to database: {db.name!r}")
    await _migrate(db)


if __name__ == "__main__":
    asyncio.run(main())
