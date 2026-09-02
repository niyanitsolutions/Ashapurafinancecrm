"""Tests for scripts/migrate_re_eligible_restart_transitions.py — merges `new_customer`
into the loan `re_eligible` row's `allowed_next_statuses` on an already-seeded DB,
without dropping the pre-existing targets.
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migrate_re_eligible_restart_transitions as migration  # noqa: E402

from app.features.workflow_engine.models import WorkflowDefinition  # noqa: E402


@pytest.fixture
def _patched_db(mock_db, monkeypatch):
    monkeypatch.setattr(migration, "get_database", lambda: mock_db)
    return mock_db


async def _seed(mock_db):
    for status, allowed_next in [
        ("re_eligible", ["credit_evaluation", "rejected", "on_hold"]),
        ("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]),
    ]:
        d = WorkflowDefinition(case_type="loan", status=status, label=status, sequence=1, allowed_next_statuses=allowed_next, audit_event="x")
        await mock_db["workflow_definitions"].insert_one(d.model_dump(by_alias=True, exclude={"id"}))


async def test_migration_merges_new_customer_without_dropping_existing(mock_db, _patched_db):
    await _seed(mock_db)
    await migration.main()

    re = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "re_eligible"})
    assert set(re["allowed_next_statuses"]) == {"new_customer", "credit_evaluation", "rejected", "on_hold"}

    ce = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "credit_evaluation"})
    assert set(ce["allowed_next_statuses"]) == {"offer_acceptance", "rejected", "re_eligible"}  # untouched

    # No Loan Management "Document Collection" row is created — it's a Leads concept.
    assert await mock_db["workflow_definitions"].count_documents({"case_type": "loan", "status": "documents_pending"}) == 0


async def test_migration_is_idempotent(mock_db, _patched_db):
    await _seed(mock_db)
    await migration.main()
    await migration.main()
    re = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "re_eligible"})
    assert len(re["allowed_next_statuses"]) == len(set(re["allowed_next_statuses"]))
