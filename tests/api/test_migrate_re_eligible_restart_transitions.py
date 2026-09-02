"""Tests for scripts/migrate_re_eligible_restart_transitions.py — brings back the loan
`documents_pending` ("Document Collection") workflow definition and merges the
restart-safe targets into `new_customer` / `re_eligible` on an already-seeded DB.
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


async def _seed_old_rows(mock_db):
    for status, label, allowed_next in [
        ("new_customer", "New Customer", ["credit_evaluation", "rejected"]),
        ("re_eligible", "Re-Eligible", ["credit_evaluation", "rejected", "on_hold"]),
        ("credit_evaluation", "Credit Evaluation", ["offer_acceptance", "rejected", "re_eligible"]),
    ]:
        d = WorkflowDefinition(
            case_type="loan", status=status, label=label, sequence=1, allowed_next_statuses=allowed_next, audit_event="x",
        )
        await mock_db["workflow_definitions"].insert_one(d.model_dump(by_alias=True, exclude={"id"}))


async def test_migration_adds_document_collection_and_merges_targets(mock_db, _patched_db):
    await _seed_old_rows(mock_db)

    await migration.main()

    dc = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "documents_pending"})
    assert dc is not None and dc["label"] == "Document Collection"
    assert set(dc["allowed_next_statuses"]) == {"credit_evaluation", "rejected", "on_hold"}

    nc = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "new_customer"})
    assert "documents_pending" in nc["allowed_next_statuses"]

    re = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "re_eligible"})
    assert {"new_customer", "documents_pending", "credit_evaluation", "rejected"} <= set(re["allowed_next_statuses"])
    assert "on_hold" in re["allowed_next_statuses"]  # pre-existing target NOT dropped

    # credit_evaluation untouched.
    ce = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "credit_evaluation"})
    assert set(ce["allowed_next_statuses"]) == {"offer_acceptance", "rejected", "re_eligible"}


async def test_migration_is_idempotent(mock_db, _patched_db):
    await _seed_old_rows(mock_db)
    await migration.main()
    await migration.main()

    assert await mock_db["workflow_definitions"].count_documents({"case_type": "loan", "status": "documents_pending"}) == 1
    re = await mock_db["workflow_definitions"].find_one({"case_type": "loan", "status": "re_eligible"})
    # No duplicate entries in the list.
    assert len(re["allowed_next_statuses"]) == len(set(re["allowed_next_statuses"]))
