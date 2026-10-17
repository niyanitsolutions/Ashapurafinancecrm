"""Mock-database migration mechanics; real MongoDB acceptance remains separate."""

import pytest
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ValidationError
from app.features.voice_assistant.staging_migration import MIGRATION_ID, apply_indexes, inspect_indexes


async def test_staging_indexes_fresh_install_repeat_and_partial_recovery(mock_db):
    db = mock_db.client["voice_staging_migration_test"]
    assert not (await inspect_indexes(db))["passed"]
    await db.tasks.create_index("voice_callback.audit_pending")
    result = await apply_indexes(db, "synthetic-backup-restore-fixture")
    assert result["passed"] and result["receipt_present"]
    receipt = await db.voice_schema_migrations.find_one({"_id": MIGRATION_ID})
    assert (await apply_indexes(db, "second-test-run"))["passed"]
    assert await db.voice_schema_migrations.find_one({"_id": MIGRATION_ID}) == receipt
    assert await db.tasks.count_documents({}) == 0


async def test_migration_never_rewrites_duplicates_or_issues_success_receipt(mock_db):
    db = mock_db.client["voice_staging_duplicates"]
    await db.tasks.insert_many([{"created_by": "same", "voice_callback": {"environment": "test", "idempotency_key": "duplicate"}} for _ in range(2)])
    with pytest.raises(DuplicateKeyError):
        await apply_indexes(db, "synthetic-backup-reference")
    assert await db.tasks.count_documents({}) == 2
    assert await db.voice_schema_migrations.count_documents({}) == 0


async def test_migration_denies_nonstaging_missing_backup_and_changed_receipt(mock_db):
    with pytest.raises(ValidationError):
        await apply_indexes(mock_db, "synthetic-backup-reference")
    db = mock_db.client["voice_staging_invalid_receipt"]
    with pytest.raises(ValidationError):
        await apply_indexes(db, "")
    await db.voice_schema_migrations.insert_one({"_id": MIGRATION_ID, "checksum": "changed"})
    with pytest.raises(ConflictError):
        await apply_indexes(db, "synthetic-backup-reference")
