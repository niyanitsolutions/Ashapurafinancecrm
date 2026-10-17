"""Versioned, additive callback indexes for explicitly isolated staging only."""

import hashlib
import json
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, ValidationError
from app.features.voice_assistant.callback_service import ensure_callback_indexes
from app.utils.datetime import utc_now

MIGRATION_ID = "voice-callback-recovery-indexes-20261017-v1"
SPECS: list[dict[str, Any]] = [
    {"key": [("created_by", 1), ("voice_callback.environment", 1), ("voice_callback.idempotency_key", 1)], "unique": True, "partialFilterExpression": {"voice_callback.idempotency_key": {"$type": "string"}}},
    {"key": [("voice_callback.environment", 1), ("voice_callback.contact_key", 1)], "unique": True, "partialFilterExpression": {"voice_callback.active": True}},
    {"key": [("voice_callback.active", 1), ("voice_callback.next_review_at", 1)]},
    {"key": [("related_entity_type", 1), ("related_entity_id", 1), ("created_at", -1)]},
    {"key": [("voice_callback.audit_pending", 1)]},
]
CHECKSUM = hashlib.sha256(json.dumps(SPECS, sort_keys=True).encode()).hexdigest()


def require_staging(db: AsyncIOMotorDatabase[Any]) -> None:
    if not db.name.startswith("voice_staging_"):
        raise ValidationError("Use an explicitly isolated voice_staging_ database; production migration is not supported by this command.")


async def inspect_indexes(db: AsyncIOMotorDatabase[Any]) -> dict[str, Any]:
    require_staging(db)
    indexes = list((await db.tasks.index_information()).values())
    results = []
    for expected in SPECS:
        matching = [index for index in indexes if list(index["key"]) == expected["key"]]
        passed = any(
            bool(index.get("unique", False)) == bool(expected.get("unique", False))
            and index.get("partialFilterExpression") == expected.get("partialFilterExpression")
            for index in matching
        )
        results.append({"keys": expected["key"], "passed": passed})
    receipt = await db.voice_schema_migrations.find_one({"_id": MIGRATION_ID})
    if receipt and receipt["checksum"] != CHECKSUM:
        raise ConflictError("Migration receipt checksum differs; investigate without overwriting history.")
    return {"migration": MIGRATION_ID, "checksum": CHECKSUM, "indexes": results,
            "passed": all(item["passed"] for item in results), "receipt_present": bool(receipt)}


async def apply_indexes(db: AsyncIOMotorDatabase[Any], backup_reference: str) -> dict[str, Any]:
    require_staging(db)
    if len(backup_reference.strip()) < 5:
        raise ValidationError("Record an isolated staging backup/restore evidence reference first.")
    await inspect_indexes(db)
    # Conflict/duplicate errors deliberately propagate. No drop, rewrite, automatic
    # duplicate removal, catalog seed, customer migration or production operation.
    await ensure_callback_indexes(db)
    result = await inspect_indexes(db)
    if not result["passed"]:
        raise ConflictError("Required callback indexes did not validate.")
    await db.voice_schema_migrations.update_one({"_id": MIGRATION_ID}, {"$setOnInsert": {
        "checksum": CHECKSUM, "applied_at": utc_now(), "backup_reference": backup_reference,
        "scope": "isolated_staging_additive_callback_indexes_only",
    }}, upsert=True)
    return await inspect_indexes(db)
