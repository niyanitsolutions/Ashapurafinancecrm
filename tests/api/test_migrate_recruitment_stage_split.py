"""Tests for scripts/migrate_recruitment_stage_split.py — remaps pre-redesign
`doc_collection_examination` / `doc_collection_re_examination` recruitment leads onto the
new flat stages. Only `recruitment_leads` (+ its `recruitment_activities` log) are
touched; idempotent.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migrate_recruitment_stage_split as migration


@pytest.fixture
def _patched_db(mock_db, monkeypatch):
    monkeypatch.setattr(migration, "get_database", lambda: mock_db)
    return mock_db


_FULL_DOCS = {
    "pan": {"file_name": "p"},
    "aadhaar": {"file_name": "a"},
    "bank_proof": {"file_name": "b"},
    "qualification": {"file_name": "q"},
    "photo": {"file_name": "ph"},
    "signature": {"method": "type", "value": "X"},
    "bank_proof_type": "passbook",
}


async def _insert(mock_db, stage, documents=None):
    res = await mock_db["recruitment_leads"].insert_one({
        "recruitment_code": f"AFS-RCT-{stage}",
        "stage": stage,
        "documents": documents,
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "is_deleted": False,
        "version": 1,
    })
    return res.inserted_id


async def test_remap_by_document_completeness(mock_db, _patched_db):
    ready = await _insert(mock_db, "doc_collection_examination", _FULL_DOCS)
    not_ready = await _insert(mock_db, "doc_collection_examination", {"pan": {"file_name": "p"}})
    reexam = await _insert(mock_db, "doc_collection_re_examination", _FULL_DOCS)
    fresh = await _insert(mock_db, "fresh", None)

    await migration.main()

    assert (await mock_db["recruitment_leads"].find_one({"_id": ready}))["stage"] == "examination"
    assert (await mock_db["recruitment_leads"].find_one({"_id": not_ready}))["stage"] == "doc_collection"
    assert (await mock_db["recruitment_leads"].find_one({"_id": reexam}))["stage"] == "re_examination"
    assert (await mock_db["recruitment_leads"].find_one({"_id": fresh}))["stage"] == "fresh"  # untouched

    activities = await mock_db["recruitment_activities"].find({"event_type": "stage_changed"}).to_list(length=50)
    assert len(activities) == 3


async def test_migration_is_idempotent(mock_db, _patched_db):
    lid = await _insert(mock_db, "doc_collection_re_examination", _FULL_DOCS)
    await migration.main()
    await migration.main()

    assert (await mock_db["recruitment_leads"].find_one({"_id": lid}))["stage"] == "re_examination"
    activities = await mock_db["recruitment_activities"].find({"event_type": "stage_changed"}).to_list(length=50)
    assert len(activities) == 1


async def test_only_recruitment_collections_touched(mock_db, _patched_db):
    await mock_db["application_workflows"].insert_one({"case_type": "loan", "current_status": "documents_pending"})
    await mock_db["application_workflows"].insert_one({"case_type": "insurance", "current_status": "policy_document"})
    await _insert(mock_db, "doc_collection_examination", _FULL_DOCS)

    await migration.main()

    loan = await mock_db["application_workflows"].find_one({"case_type": "loan"})
    ins = await mock_db["application_workflows"].find_one({"case_type": "insurance"})
    assert loan["current_status"] == "documents_pending"
    assert ins["current_status"] == "policy_document"
