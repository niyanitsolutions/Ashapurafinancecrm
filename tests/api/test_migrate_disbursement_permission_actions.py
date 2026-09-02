"""Tests for scripts/migrate_disbursement_permission_actions.py — backfills `approve`
and `reject` onto the `loan_management:applications` / `insurance_management:applications`
permission-catalog rows on databases first seeded before those actions existed in the
seed's `case_actions` list. Same standalone-CLI test shape as
test_migrate_decouple_leads_tasks_grants.py.
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migrate_disbursement_permission_actions as migration  # noqa: E402

from app.features.access_control.models import Permission  # noqa: E402


@pytest.fixture
def _patched_db(mock_db, monkeypatch):
    monkeypatch.setattr(migration, "get_database", lambda: mock_db)
    return mock_db


async def _insert_permission(mock_db, module, resource, actions):
    doc = Permission(module=module, resource=resource, actions=actions, label=resource).model_dump(by_alias=True, exclude={"id"})
    await mock_db["permissions"].insert_one(doc)


async def test_backfills_approve_and_reject_onto_stale_rows(mock_db, _patched_db):
    await _insert_permission(mock_db, "loan_management", "applications", ["view", "edit", "assign"])
    await _insert_permission(mock_db, "insurance_management", "applications", ["view", "edit", "assign"])
    # An unrelated row that must not change.
    await _insert_permission(mock_db, "leads", "leads", ["view", "create", "edit"])

    await migration.main()

    loan = await mock_db["permissions"].find_one({"module": "loan_management", "resource": "applications"})
    ins = await mock_db["permissions"].find_one({"module": "insurance_management", "resource": "applications"})
    leads = await mock_db["permissions"].find_one({"module": "leads", "resource": "leads"})

    assert set(loan["actions"]) == {"view", "edit", "assign", "approve", "reject"}
    assert set(ins["actions"]) == {"view", "edit", "assign", "approve", "reject"}
    assert set(leads["actions"]) == {"view", "create", "edit"}  # untouched


async def test_idempotent_second_run_is_noop(mock_db, _patched_db):
    await _insert_permission(mock_db, "loan_management", "applications", ["view", "edit", "approve", "reject", "assign"])

    await migration.main()
    await migration.main()

    loan = await mock_db["permissions"].find_one({"module": "loan_management", "resource": "applications"})
    assert sorted(loan["actions"]) == sorted(["view", "edit", "approve", "reject", "assign"])


async def test_missing_row_is_skipped_not_created(mock_db, _patched_db):
    await migration.main()
    assert await mock_db["permissions"].count_documents({}) == 0
