"""Owner-only soft-delete, centralized Bin listing, restore, and the 30-day purge.

Every write here is only ever reached through `Depends(require_owner)` (see router) — an
Employee cannot call any of it. Deletion is ALWAYS soft: the row keeps all its data and
relationships and simply gains `is_deleted=True` (via `BaseRepository.soft_delete`), so
it vanishes from every normal list/count for free and can be restored intact. Physical
removal happens only in `purge_expired`, run daily by the Arq worker, and only for
records whose 30-day retention has elapsed.
"""

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ConfigDict
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.bin.constants import RETENTION_DAYS, BinAuditEvent
from app.features.bin.models import BinEntry
from app.features.bin.registry import (
    DeletableResource,
    all_resources,
    get_resource,
    record_code,
    record_summary,
    stage_label,
)
from app.features.bin.repository import BinEntryRepository
from app.shared.audit_log import write_audit_log
from app.shared.base_document import BaseDocument
from app.shared.base_repository import BaseRepository
from app.utils.datetime import add_days, utc_now
from app.utils.helpers import to_object_id


class _RawDoc(BaseDocument):
    model_config = ConfigDict(extra="allow", populate_by_name=True, arbitrary_types_allowed=True)


class _CollectionRepo(BaseRepository[_RawDoc]):
    """Generic typed access to any collection — for the cross-collection soft-delete /
    restore primitives the Bin needs without importing every feature's model."""

    model = _RawDoc

    def __init__(self, db: AsyncIOMotorDatabase[Any], collection_name: str) -> None:
        super().__init__(db)
        self.collection_name = collection_name


class BinService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._entries = BinEntryRepository(db)

    # ---------------------------------------------------------------- helpers

    def _repo(self, collection: str) -> _CollectionRepo:
        return _CollectionRepo(self._db, collection)

    async def _actor_name(self, actor: User) -> str | None:
        doc = await self._db["users"].find_one({"_id": to_object_id(actor.require_id())})
        if not doc:
            return None
        name = " ".join(str(doc[f]) for f in ("first_name", "last_name") if doc.get(f)).strip()
        return name or doc.get("full_name") or doc.get("mobile")

    async def _load_target(self, resource: DeletableResource, document_id: str) -> dict[str, Any]:
        doc = await self._db[resource.collection].find_one({"_id": to_object_id(document_id), "is_deleted": False})
        if doc is None or not resource.matches(doc):
            raise NotFoundError("Record not found (or already deleted).")
        return dict(doc)

    def _build_entry(self, resource: DeletableResource, doc: dict[str, Any], actor: User, actor_name: str | None, now: datetime) -> BinEntry:
        return BinEntry(
            resource_key=resource.key, target_collection=resource.collection, document_id=str(doc["_id"]),
            module_label=resource.module_label, stage_label=stage_label(resource, doc),
            record_code=record_code(resource, doc), record_summary=record_summary(resource, doc),
            original_status=doc.get("status"),
            deleted_by=actor.require_id(), deleted_by_name=actor_name, deleted_at=now,
            purge_at=add_days(now, RETENTION_DAYS), created_by=actor.require_id(),
        )

    # ---------------------------------------------------------------- delete

    async def delete(self, resource_key: str, document_id: str, actor: User) -> BinEntry:
        resource = get_resource(resource_key)
        doc = await self._load_target(resource, document_id)
        if resource.guard is not None:
            await resource.guard(doc, self._db)

        now = utc_now()
        if not await self._repo(resource.collection).soft_delete(document_id, deleted_by=actor.require_id()):
            raise ConflictError("Record could not be deleted — it may already be in the Bin.")
        entry = self._build_entry(resource, doc, actor, await self._actor_name(actor), now)
        entry_id = await self._entries.insert(entry)
        await write_audit_log(
            self._db, event_type=BinAuditEvent.RECORD_DELETED, user_id=actor.require_id(),
            metadata={"resource_key": resource_key, "collection": resource.collection, "document_id": document_id, "record_code": entry.record_code},
        )
        found = await self._entries.find_by_id(entry_id)
        assert found is not None
        return found

    async def bulk_delete(self, resource_key: str, document_ids: list[str], actor: User) -> dict[str, Any]:
        resource = get_resource(resource_key)
        if not document_ids:
            raise ValidationError("No records selected.")
        if len(document_ids) > 500:
            raise ValidationError("At most 500 records can be deleted at once.")

        deletable: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for document_id in dict.fromkeys(document_ids):  # de-dup, keep order
            try:
                doc = await self._load_target(resource, document_id)
                if resource.guard is not None:
                    await resource.guard(doc, self._db)
                deletable.append(doc)
            except (NotFoundError, ValidationError) as exc:
                skipped.append({"document_id": document_id, "reason": str(exc)})

        if not deletable:
            return {"deleted": [], "skipped": skipped}

        now = utc_now()
        actor_name = await self._actor_name(actor)
        ids = [str(d["_id"]) for d in deletable]
        flipped = set(await self._repo(resource.collection).soft_delete_many(ids, deleted_by=actor.require_id()))
        entries = [self._build_entry(resource, d, actor, actor_name, now) for d in deletable if str(d["_id"]) in flipped]
        if entries:
            await self._entries.collection.insert_many([e.model_dump(by_alias=True, exclude={"id"}) for e in entries])
        await write_audit_log(
            self._db, event_type=BinAuditEvent.RECORDS_BULK_DELETED, user_id=actor.require_id(),
            metadata={"resource_key": resource_key, "collection": resource.collection, "document_ids": list(flipped), "count": len(flipped)},
        )
        return {"deleted": list(flipped), "skipped": skipped}

    # ---------------------------------------------------------------- list

    async def list_bin(self, *, resource_key: str | None, search: str | None, skip: int, limit: int) -> tuple[list[BinEntry], int]:
        return await self._entries.list_active(resource_key=resource_key, search=search, skip=skip, limit=limit)

    def resources(self) -> list[dict[str, str]]:
        return [{"key": r.key, "module_label": r.module_label} for r in all_resources()]

    # ---------------------------------------------------------------- restore

    async def restore(self, bin_entry_id: str, actor: User) -> BinEntry:
        entry = await self._entries.find_by_id(bin_entry_id)
        if entry is None:
            raise NotFoundError("Bin entry not found.")
        if entry.restored_at is not None:
            raise ConflictError("This record has already been restored.")
        if entry.purged_at is not None:
            raise ConflictError("This record has been permanently deleted and cannot be restored.")
        try:
            restored = await self._repo(entry.target_collection).restore(
                entry.document_id, restored_by=actor.require_id(), restore_status=entry.original_status
            )
        except DuplicateKeyError as exc:
            raise ConflictError(
                "Can't restore this record — another record now uses one of its unique values "
                f"(e.g. code or mobile number). {exc.details.get('keyValue') if exc.details else ''}".strip()
            ) from exc
        if not restored:
            raise ConflictError("The underlying record is no longer in a restorable state.")
        now = utc_now()
        await self._entries.update(bin_entry_id, {"restored_at": now, "restored_by": actor.require_id()}, updated_by=actor.require_id())
        await write_audit_log(
            self._db, event_type=BinAuditEvent.RECORD_RESTORED, user_id=actor.require_id(),
            metadata={"resource_key": entry.resource_key, "collection": entry.target_collection, "document_id": entry.document_id, "record_code": entry.record_code},
        )
        found = await self._entries.find_by_id(bin_entry_id)
        assert found is not None
        return found

    # ---------------------------------------------------------------- 30-day purge

    async def purge_expired(self, now: datetime) -> dict[str, int]:
        due = await self._entries.find_due_for_purge(now)
        purged = 0
        failed = 0
        for entry in due:
            try:
                resource = get_resource(entry.resource_key)
                child_counts: dict[str, int] = {}
                for child_collection, fk in resource.child_collections:
                    result = await self._db[child_collection].delete_many({fk: entry.document_id})
                    child_counts[child_collection] = result.deleted_count
                await self._db[entry.target_collection].delete_one({"_id": to_object_id(entry.document_id)})
                await self._entries.update(entry.require_id(), {"purged_at": now})
                await write_audit_log(
                    self._db, event_type=BinAuditEvent.RECORD_PURGED, user_id=None,
                    metadata={
                        "resource_key": entry.resource_key, "collection": entry.target_collection,
                        "document_id": entry.document_id, "record_code": entry.record_code, "child_counts": child_counts,
                    },
                )
                purged += 1
            except Exception:  # noqa: BLE001 — one bad entry must never stall the batch
                failed += 1
        return {"purged": purged, "failed": failed, "considered": len(due)}
