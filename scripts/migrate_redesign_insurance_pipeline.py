"""Insurance "Policy Leads" redesign — Phase 3: rewrite the insurance workflow and
remap every live insurance case.

FULL REPLACE of the decision-064 insurance lifecycle. This script:

  1. Rewrites `workflow_definitions` rows for `case_type == "insurance"` to the new
     graph (fresh_lead -> policy_document -> policy_login -> policy_issued, + re_eligible
     from rejected, + on_hold from every non-terminal), using `$set` so an
     already-seeded row picks up the change. Deletes the rows for the retired statuses
     (underwriting / medical_verification / additional_documents / premium_acceptance /
     policy_generation).
  2. Remaps every live `application_workflows` row (`case_type == "insurance"`):
       application_submitted                                   -> fresh_lead
       documents_pending | underwriting | medical_verification
         | additional_documents                                -> policy_document
       premium_acceptance | policy_generation                  -> policy_login
       policy_issued | rejected | on_hold                      -> unchanged
     Also remaps `on_hold_previous_status` by the same table, and appends an
     `application_status_history` row noting the remap.

**Loan is never touched.** Idempotent: a case already on a new status is left alone;
re-running only re-asserts the workflow-definition rows.

Run from repo root: python scripts/migrate_redesign_insurance_pipeline.py
Run from backend/:  python ../scripts/migrate_redesign_insurance_pipeline.py
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config.database import get_database
from app.features.workflow_engine.constants import (
    ON_HOLD_STATUS,
    InsuranceAuditEvent,
    InsuranceStatus,
    WorkflowAuditEvent,
)

_REMAP: dict[str, str] = {
    "application_submitted": InsuranceStatus.FRESH_LEAD,
    "documents_pending": InsuranceStatus.POLICY_DOCUMENT,
    "underwriting": InsuranceStatus.POLICY_DOCUMENT,
    "medical_verification": InsuranceStatus.POLICY_DOCUMENT,
    "additional_documents": InsuranceStatus.POLICY_DOCUMENT,
    "premium_acceptance": InsuranceStatus.POLICY_LOGIN,
    "policy_generation": InsuranceStatus.POLICY_LOGIN,
}
_RETIRED_STATUSES = ("underwriting", "medical_verification", "additional_documents", "premium_acceptance", "policy_generation")

# (status, label, sequence, allowed_next, employee_editable, audit_event, notification_key)
_INSURANCE_ROWS = [
    (InsuranceStatus.FRESH_LEAD, "Fresh Lead", 1, [InsuranceStatus.POLICY_DOCUMENT, InsuranceStatus.REJECTED], InsuranceAuditEvent.CASE_CREATED, "insurance_case.created"),
    (InsuranceStatus.POLICY_DOCUMENT, "Policy Document", 2, [InsuranceStatus.POLICY_LOGIN, InsuranceStatus.REJECTED], InsuranceAuditEvent.POLICY_DOCUMENT_STARTED, "insurance_case.policy_document_started"),
    (InsuranceStatus.POLICY_LOGIN, "Policy Login", 3, [InsuranceStatus.POLICY_ISSUED, InsuranceStatus.REJECTED], InsuranceAuditEvent.POLICY_LOGIN_STARTED, "insurance_case.policy_login_started"),
    (InsuranceStatus.POLICY_ISSUED, "Policy Issued", 4, [], InsuranceAuditEvent.POLICY_ISSUED, "insurance_case.policy_issued"),
    (InsuranceStatus.RE_ELIGIBLE, "Re-Eligible", 5, [InsuranceStatus.FRESH_LEAD, InsuranceStatus.POLICY_DOCUMENT, InsuranceStatus.REJECTED], InsuranceAuditEvent.MARKED_RE_ELIGIBLE, "insurance_case.marked_re_eligible"),
    (InsuranceStatus.REJECTED, "Application Rejected", 6, [InsuranceStatus.RE_ELIGIBLE], InsuranceAuditEvent.REJECTED, "insurance_case.rejected"),
]
_ALLOWED_PREVIOUS = {
    InsuranceStatus.POLICY_DOCUMENT: [InsuranceStatus.FRESH_LEAD],
    InsuranceStatus.POLICY_LOGIN: [InsuranceStatus.POLICY_DOCUMENT],
}

# `fresh_lead` / `policy_document` / `policy_login` / `re_eligible` are BRAND-NEW statuses
# with no pre-existing row, so this migration's `$set` upsert *creates* them. Every
# lookup in the app (`WorkflowDefinitionRepository.find_by_case_type_status`, the same
# `{"is_deleted": False}` convention `BaseRepository` uses everywhere) filters on the
# soft-delete fields — an upserted row that omits them is invisible, and
# `WorkflowEngine.get_definition` then 404s on every transition. So the payload must
# carry the full `BaseDocument` lifecycle shape, exactly like a `WorkflowDefinition`
# inserted by `scripts/seed.py` does.
_BASE_DOCUMENT_FIELDS: dict[str, object] = {
    "is_deleted": False, "deleted_at": None, "deleted_by": None,
    "version": 1, "created_by": None, "updated_by": None,
}


async def _rewrite_definitions(db) -> None:
    definitions = db["workflow_definitions"]
    for status, label, sequence, allowed_next, audit_event, notification_key in _INSURANCE_ROWS:
        full_next = [*allowed_next, ON_HOLD_STATUS] if status in InsuranceStatus.RESUMABLE else allowed_next
        payload = {
            **_BASE_DOCUMENT_FIELDS,
            "case_type": "insurance", "status": status, "label": label, "sequence": sequence,
            "allowed_next_statuses": full_next, "allowed_previous_statuses": _ALLOWED_PREVIOUS.get(status, []),
            "required_permission": "insurance_management:applications:edit", "customer_editable": False,
            "employee_editable": status not in InsuranceStatus.TERMINAL, "audit_event": audit_event,
            "notification_trigger_key": notification_key, "reminder_trigger_key": None,
        }
        await definitions.update_one({"case_type": "insurance", "status": status}, {"$set": payload}, upsert=True)

    await definitions.update_one(
        {"case_type": "insurance", "status": ON_HOLD_STATUS},
        {"$set": {
            **_BASE_DOCUMENT_FIELDS,
            "case_type": "insurance", "status": ON_HOLD_STATUS, "label": "On Hold", "sequence": len(_INSURANCE_ROWS) + 1,
            "allowed_next_statuses": list(InsuranceStatus.RESUMABLE), "allowed_previous_statuses": [],
            "required_permission": "insurance_management:applications:edit", "customer_editable": False,
            "employee_editable": True, "audit_event": WorkflowAuditEvent.CASE_ON_HOLD,
            "notification_trigger_key": None, "reminder_trigger_key": None,
        }},
        upsert=True,
    )

    result = await definitions.delete_many({"case_type": "insurance", "status": {"$in": list(_RETIRED_STATUSES)}})
    print(f"workflow_definitions: rewrote {len(_INSURANCE_ROWS) + 1} insurance rows, removed {result.deleted_count} retired rows")


async def _remap_cases(db) -> None:
    workflows = db["application_workflows"]
    history = db["application_status_history"]
    cases = await workflows.find({"case_type": "insurance"}).to_list(length=100_000)

    remapped = 0
    for case in cases:
        updates: dict[str, object] = {}
        old_status = case.get("current_status")
        new_status = _REMAP.get(old_status)
        if new_status is not None and new_status != old_status:
            updates["current_status"] = new_status
        old_prev = case.get("on_hold_previous_status")
        new_prev = _REMAP.get(old_prev) if old_prev else None
        if new_prev is not None and new_prev != old_prev:
            updates["on_hold_previous_status"] = new_prev
        if not updates:
            continue
        await workflows.update_one({"_id": case["_id"]}, {"$set": updates})
        if "current_status" in updates:
            await history.insert_one({
                "application_workflow_id": str(case["_id"]), "case_type": "insurance",
                "from_status": old_status, "to_status": new_status,
                "remarks": "Pipeline redesign — remapped to the new Policy Leads flow.",
                "created_by": None, "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC),
                "is_deleted": False, "version": 1,
            })
        remapped += 1
        print(f"  case {case.get('case_code', case['_id'])}: {old_status} -> {updates.get('current_status', old_status)}")

    print(f"\napplication_workflows: remapped {remapped} of {len(cases)} insurance case(s). Loan untouched.")


async def main() -> None:
    db = get_database()
    print(f"Connected to database: {db.name!r}")
    await _rewrite_definitions(db)
    await _remap_cases(db)


if __name__ == "__main__":
    asyncio.run(main())
