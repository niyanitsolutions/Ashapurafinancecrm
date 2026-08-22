"""Production bug fix — Loan Management workflow redesign (see docs/decisions/DECISIONS.md).

Two independent parts, run together in one invocation, each safe to re-run:

**Part 1 — WorkflowDefinition graph update (the mechanism that actually matters).**
`scripts/seed.py::seed_workflow_definitions` writes with `$setOnInsert`, which only
applies on a brand-new document — editing its Loan row tuples has ZERO effect on an
already-seeded database. This part `$set`-updates the `allowed_next_statuses` on every
existing Loan `WorkflowDefinition` row whose transition graph changed
(`new_customer`, `additional_documents`, `credit_evaluation`, `on_hold`), and upserts the
two brand-new rows (`rv_ov_ref`, `re_eligible`) via the same `$setOnInsert` seed.py
already uses elsewhere (safe either way — insert if missing, no-op if already present
from a prior run of this script). This MUST run before the new backend code is deployed:
old code can't reach `rv_ov_ref`/`re_eligible` without these rows existing, and new code
transitioning `new_customer -> credit_evaluation` directly would fail
`assert_transition_allowed` against a database still carrying the old
`new_customer -> [documents_pending]` graph.

**Part 2 — report only, never auto-applied.** Any existing `ApplicationWorkflow` sitting
in `current_status="documents_pending"` (the old, now-retired mandatory step) is reported
with its `pending_document_type_ids` state and a proposed forward move to
`credit_evaluation` — but NOTHING is changed. A human must review each one (documents may
genuinely still be outstanding) and apply the move manually via the normal
`PATCH /loan-cases/{id}/status` staff action, exactly like any other case update, once
satisfied it's safe. This script never deletes or destructively rewrites a case.

Run from repo root: python scripts/migrate_redesign_loan_pipeline.py
Run from backend/:  python ../scripts/migrate_redesign_loan_pipeline.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.workflow_engine.constants import LoanAuditEvent, LoanStatus, ON_HOLD_STATUS
from app.features.workflow_engine.models import WorkflowDefinition

# (status, new allowed_next_statuses) — must match scripts/seed.py's current loan_rows
# for these four statuses exactly, or the live database and the seed source of truth for
# a fresh install would silently diverge.
_UPDATED_ALLOWED_NEXT: dict[str, list[str]] = {
    LoanStatus.NEW_CUSTOMER: [LoanStatus.CREDIT_EVALUATION],
    LoanStatus.CREDIT_EVALUATION: [LoanStatus.OFFER_ACCEPTANCE, LoanStatus.REJECTED, LoanStatus.RE_ELIGIBLE, ON_HOLD_STATUS],
    LoanStatus.ADDITIONAL_DOCUMENTS: [LoanStatus.RV_OV_REF, ON_HOLD_STATUS],
    ON_HOLD_STATUS: list(LoanStatus.RESUMABLE),
}

# Built via the real model (not a raw dict) so every `BaseDocument` field — critically
# `is_deleted` — is actually present on the inserted document. A raw dict missing
# `is_deleted` silently fails every later read, since every read path filters on
# `is_deleted: False`; a document with the key simply absent never matches that filter.
_NEW_ROWS = [
    WorkflowDefinition(
        case_type="loan", status=LoanStatus.RV_OV_REF, label="RV/OV/Ref", sequence=5,
        allowed_next_statuses=[LoanStatus.ESIGN_NACH_KYC, ON_HOLD_STATUS], allowed_previous_statuses=[],
        required_permission="loan_management:applications:edit", customer_editable=False, employee_editable=True,
        audit_event=LoanAuditEvent.ADDITIONAL_DOCS_VERIFIED, notification_trigger_key="loan_case.additional_docs_verified",
        reminder_trigger_key=None,
    ),
    WorkflowDefinition(
        case_type="loan", status=LoanStatus.RE_ELIGIBLE, label="Re-Eligible", sequence=10,
        allowed_next_statuses=[LoanStatus.CREDIT_EVALUATION, LoanStatus.REJECTED, ON_HOLD_STATUS], allowed_previous_statuses=[],
        required_permission="loan_management:applications:edit", customer_editable=False, employee_editable=True,
        audit_event=LoanAuditEvent.MARKED_RE_ELIGIBLE, notification_trigger_key="loan_case.marked_re_eligible",
        reminder_trigger_key=None,
    ),
]


async def main() -> None:
    db = get_database()
    definitions = db["workflow_definitions"]
    workflows = db["application_workflows"]

    print(f"Connected to database: {db.name!r}")

    # ---- Part 1: fix the transition graph on existing rows ----
    print("\n== Part 1: updating existing WorkflowDefinition rows (loan) ==")
    for status, allowed_next in _UPDATED_ALLOWED_NEXT.items():
        existing = await definitions.find_one({"case_type": "loan", "status": status})
        if existing is None:
            print(f"  SKIP {status!r}: no existing row found (a fresh install will get it correctly from scripts/seed.py instead).")
            continue
        result = await definitions.update_one(
            {"case_type": "loan", "status": status}, {"$set": {"allowed_next_statuses": allowed_next}}
        )
        print(f"  {status!r}: allowed_next_statuses -> {allowed_next} (matched={result.matched_count}, modified={result.modified_count})")

    print("\n== Part 1: upserting new WorkflowDefinition rows (rv_ov_ref, re_eligible) ==")
    for row in _NEW_ROWS:
        payload = row.model_dump(by_alias=True, exclude={"id"})
        result = await definitions.update_one(
            {"case_type": "loan", "status": row.status}, {"$setOnInsert": payload}, upsert=True
        )
        action = "inserted" if result.upserted_id else "already present, unchanged"
        print(f"  {row.status!r}: {action}")

    # ---- Part 2: report (never apply) documents_pending cases ----
    print("\n== Part 2: reporting existing cases stuck in the retired 'documents_pending' status ==")
    stuck = await workflows.find({"case_type": "loan", "current_status": LoanStatus.DOCUMENTS_PENDING, "is_deleted": False}).to_list(length=1000)
    if not stuck:
        print("  None found. Nothing to review.")
    else:
        print(f"  Found {len(stuck)} case(s) still in 'documents_pending' — NOT modified. Review each and, once satisfied\n"
              "  its documents are actually in order, move it forward yourself via the normal\n"
              "  PATCH /loan-cases/{id}/status staff action (target: 'credit_evaluation'):\n")
        for case in stuck:
            pending = case.get("pending_document_type_ids") or []
            print(f"    case_code={case.get('case_code')!r}  id={case['_id']}  pending_document_type_ids={pending}")

    print("\nDone. No case documents were created, deleted, or destructively modified.")


if __name__ == "__main__":
    asyncio.run(main())
