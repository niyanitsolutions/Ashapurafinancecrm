"""Centralized Bin — the 30-day automatic permanent-deletion worker job
(`purge_expired_bin_entries` -> `BinService.purge_expired`).
"""

from datetime import timedelta

import pytest

from app.features.bin.service import BinService
from app.utils.datetime import utc_now
from app.utils.helpers import to_object_id
from app.worker.tasks.bin_cleanup import purge_expired_bin_entries


@pytest.fixture(autouse=True)
def _patch_worker_db(mock_db, monkeypatch):
    monkeypatch.setattr("app.worker.tasks.bin_cleanup.get_database", lambda: mock_db)


async def _binned_lead(mock_db, *, code, deleted_days_ago):
    now = utc_now()
    lead_id = (
        await mock_db["leads"].insert_one(
            {"lead_code": code, "full_name": "Purge Me", "mobile": f"96{code[-8:]}", "source_id": "s", "product_category": "loan",
             "product_id": "p", "stage": "fresh", "status": "deleted", "is_deleted": True, "deleted_at": now, "deleted_by": "owner",
             "created_at": now, "updated_at": now, "version": 2}
        )
    ).inserted_id
    await mock_db["lead_notes"].insert_one({"lead_id": str(lead_id), "text": "a note", "is_deleted": False, "status": "active", "created_at": now, "updated_at": now, "version": 1})
    await mock_db["lead_activities"].insert_one({"lead_id": str(lead_id), "event_type": "created", "is_deleted": False, "status": "active", "created_at": now, "updated_at": now, "version": 1})
    deleted_at = now - timedelta(days=deleted_days_ago)
    await mock_db["bin_entries"].insert_one(
        {"resource_key": "leads", "target_collection": "leads", "document_id": str(lead_id), "module_label": "Leads",
         "stage_label": "Fresh", "record_code": code, "record_summary": "Purge Me", "deleted_by": "owner", "deleted_by_name": "Owner",
         "deleted_at": deleted_at, "purge_at": deleted_at + timedelta(days=30), "restored_at": None, "purged_at": None,
         "is_deleted": False, "status": "active", "created_at": deleted_at, "updated_at": deleted_at, "version": 1}
    )
    return str(lead_id)


async def test_purge_removes_expired_record_and_owned_children_only(mock_db):
    expired_id = await _binned_lead(mock_db, code="AFS-LEAD-EXP1", deleted_days_ago=31)
    fresh_id = await _binned_lead(mock_db, code="AFS-LEAD-FRESH", deleted_days_ago=2)
    # An unrelated ACTIVE lead that must never be touched.
    now = utc_now()
    active_id = (
        await mock_db["leads"].insert_one(
            {"lead_code": "AFS-LEAD-ACTIVE", "full_name": "Keep", "mobile": "9600000000", "source_id": "s", "product_category": "loan",
             "product_id": "p", "stage": "fresh", "status": "active", "is_deleted": False, "created_at": now, "updated_at": now, "version": 1}
        )
    ).inserted_id
    audit_before = await mock_db["audit_logs"].count_documents({})

    result = await purge_expired_bin_entries({})
    assert result["purged"] == 1 and result["failed"] == 0

    # Expired lead + its notes/activities are physically gone.
    assert await mock_db["leads"].find_one({"_id": to_object_id(expired_id)}) is None
    assert await mock_db["lead_notes"].count_documents({"lead_id": expired_id}) == 0
    assert await mock_db["lead_activities"].count_documents({"lead_id": expired_id}) == 0
    assert (await mock_db["bin_entries"].find_one({"document_id": expired_id}))["purged_at"] is not None

    # The still-in-retention lead and the unrelated active lead are untouched.
    assert await mock_db["leads"].find_one({"_id": to_object_id(fresh_id)}) is not None
    assert await mock_db["leads"].find_one({"_id": active_id}) is not None

    # audit_logs only grew (append-only) — the purge writes a RECORD_PURGED row, never deletes.
    assert await mock_db["audit_logs"].count_documents({}) >= audit_before
    assert await mock_db["audit_logs"].count_documents({"event_type": "bin_record_purged"}) == 1


async def test_purge_skips_restored_and_already_purged_entries(mock_db):
    lead_id = await _binned_lead(mock_db, code="AFS-LEAD-RESTORED", deleted_days_ago=40)
    await mock_db["bin_entries"].update_one({"document_id": lead_id}, {"$set": {"restored_at": utc_now()}})

    result = await BinService(mock_db).purge_expired(utc_now())
    assert result["purged"] == 0
    assert await mock_db["leads"].find_one({"_id": to_object_id(lead_id)}) is not None
