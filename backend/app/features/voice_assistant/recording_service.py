import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from cryptography.fernet import InvalidToken
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.recording_schemas import TranscriptInput
from app.features.voice_assistant.recording_storage import PrivateRecordingStorage, validate_wav
from app.features.voice_assistant.repository import VoiceRepository, public
from app.features.voice_assistant.service import VoiceService
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def ensure_recording_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_recordings.create_index(
        [("owner_user_id", 1), ("idempotency_key", 1)], unique=True
    )
    await db.voice_recordings.create_index([("call_id", 1), ("created_at", -1)])
    await db.voice_recordings.create_index([("call_owner_user_id", 1), ("created_at", -1)])
    await db.voice_recordings.create_index([("status", 1), ("expires_at", 1)])


def recording_public(doc: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "_id",
        "version",
        "call_id",
        "direction",
        "call_provider",
        "status",
        "origin",
        "duration_seconds",
        "size_bytes",
        "sample_rate",
        "channels",
        "encoding",
        "created_at",
        "updated_at",
        "expires_at",
        "verified_at",
        "recovered_at",
        "deleted_at",
        "delete_reason",
        "transcript_status",
        "consent_verification",
        "error",
        "language",
        "call_outcome",
    }
    fields = {key: value for key, value in doc.items() if key in allowed}
    return public(fields)


class RecordingService:
    def __init__(
        self, db: AsyncIOMotorDatabase[Any], storage: PrivateRecordingStorage | None = None
    ) -> None:
        self.db = db
        self.storage = storage or PrivateRecordingStorage()
        self.repo = VoiceRepository(db)

    async def audit(self, actor_id: str, action: str, record_id: str) -> None:
        await write_audit_log(
            self.db,
            event_type=f"voice_assistant.recording_{action}",
            user_id=actor_id,
            metadata={"record_id": record_id},
        )

    async def get(self, record_id: str, actor: User, *, playable: bool = False) -> dict[str, Any]:
        doc = await self.repo.get("voice_recordings", record_id)
        # Recheck the owning call, not just a derivative's creator identifier.
        await VoiceService(self.db).call(doc["call_id"], actor)
        if playable and (doc["status"] != "completed" or doc["expires_at"] <= utc_now()):
            raise ForbiddenError("Recording is expired, deleted, pending or unavailable.")
        return doc

    async def list(
        self,
        actor: User,
        *,
        page: int,
        status: str | None,
        call_id: str | None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"is_deleted": False}
        if actor.role != "owner":
            # The artifact always inherits the call's owner, not the importing operator.
            query["call_owner_user_id"] = actor.require_id()
        if status == "expired":
            query["status"] = {"$nin": ["deleted", "deletion_pending"]}
            query["expires_at"] = {"$lte": utc_now()}
        elif status:
            query["status"] = status
            if status == "completed":
                query["expires_at"] = {"$gt": utc_now()}
        if any(value is not None and value.tzinfo is None for value in (since, until)):
            raise ValidationError("Recording date filters require timezone-aware timestamps.")
        if since and until and since >= until:
            raise ValidationError("Recording start date must precede the exclusive end date.")
        if since or until:
            query["created_at"] = {
                **({"$gte": since} if since else {}),
                **({"$lt": until} if until else {}),
            }
        if call_id:
            await VoiceService(self.db).call(call_id, actor)
            query["call_id"] = call_id
        total = await self.db.voice_recordings.count_documents(query)
        docs = (
            await self.db.voice_recordings.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        items = []
        for doc in docs:
            # Exclude derivatives whose authoritative call was removed or moved out of scope.
            try:
                await VoiceService(self.db).call(doc["call_id"], actor)
            except (NotFoundError, ForbiddenError):
                continue
            item = recording_public(doc)
            if item["expires_at"] <= utc_now() and item["status"] == "completed":
                item["status"] = "expired"
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "storage": "configured_not_externally_verified"
            if self.storage.config.recordings_dir
            else "not_configured",
            "live_capture": "blocked",
            "transcription_engine": "not_approved",
        }

    async def import_recording(
        self,
        actor: User,
        *,
        call_id: str,
        data: bytes,
        idempotency_key: str,
        consent_reference: str,
        retention_days: int,
    ) -> dict[str, Any]:
        call = await VoiceService(self.db).call(call_id, actor)
        if call["status"] not in {"completed", "failed", "missed", "cancelled"}:
            raise ConflictError("Import artifacts only for ended calls; live capture is blocked.")
        if not self.storage.config.recordings_dir:
            raise ValidationError(
                "Private storage is not configured. Set VOICE_RECORDINGS_DIR before importing audio."
            )
        metadata = await asyncio.to_thread(validate_wav, data)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "call_id": call_id,
                    "sha256": metadata["sha256"],
                    "consent_reference": consent_reference,
                    "retention_days": retention_days,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        key = {"owner_user_id": actor.require_id(), "idempotency_key": idempotency_key}
        previous = await self.db.voice_recordings.find_one(key)
        if previous:
            await self.get(str(previous["_id"]), actor)
            if previous.get("request_fingerprint") != fingerprint:
                raise ConflictError(
                    "Import key belongs to a different artifact or retention request."
                )
            return recording_public(previous)
        now = utc_now()
        doc = {
            "_id": ObjectId(),
            **key,
            **metadata,
            "request_fingerprint": fingerprint,
            "call_id": call_id,
            "call_owner_user_id": call["owner_user_id"],
            "direction": call["direction"],
            "call_provider": call["provider"],
            "language": call.get("language", "en"),
            "call_outcome": call["status"],
            "status": "pending",
            "origin": "imported_artifact",
            "transcript_status": "not_available",
            "consent_reference": consent_reference,
            "consent_verification": "operator_attested_not_independently_verified",
            "expires_at": now + timedelta(days=retention_days),
            "lease_until": now + timedelta(seconds=120),
            "created_at": now,
            "updated_at": now,
            "created_by": actor.require_id(),
            "updated_by": actor.require_id(),
            "version": 1,
            "is_deleted": False,
        }
        try:
            await self.db.voice_recordings.insert_one(doc)
        except DuplicateKeyError:
            previous = await self.db.voice_recordings.find_one(key)
            if previous is None or previous["request_fingerprint"] != fingerprint:
                raise ConflictError(
                    "Concurrent import changed. Retry with the same artifact/key."
                ) from None
            return recording_public(previous)
        record_id = str(doc["_id"])
        await self.audit(actor.require_id(), "import_started", record_id)
        try:
            await asyncio.to_thread(self.storage.put, record_id, data)
            stored = await asyncio.to_thread(self.storage.read, record_id, metadata["sha256"])
            if len(stored) != metadata["size_bytes"]:
                raise ValueError("stored artifact size")
        except (OSError, ValueError, InvalidToken, ValidationError):
            await self.repo.update(
                "voice_recordings",
                doc,
                {"status": "failed", "error": "storage_or_integrity_failed"},
                actor.require_id(),
            )
            await self.audit(actor.require_id(), "import_failed", record_id)
            raise ValidationError(
                "Recording storage/verification failed. Review private storage and retry recovery; no completed audio was declared."
            ) from None
        result = await self.repo.update(
            "voice_recordings",
            doc,
            {"status": "completed", "verified_at": utc_now()},
            actor.require_id(),
        )
        await self.audit(actor.require_id(), "import_completed", record_id)
        return recording_public(result)

    async def audio(self, record_id: str, actor: User, *, download: bool) -> bytes:
        doc = await self.get(record_id, actor, playable=True)
        try:
            data = await asyncio.to_thread(self.storage.read, record_id, doc["sha256"])
        except (OSError, ValueError, InvalidToken, ValidationError):
            await self.audit(actor.require_id(), "playback_failed", record_id)
            raise ValidationError(
                "Recording artifact is unavailable or failed integrity verification. Contact the storage operator."
            ) from None
        latest = await self.get(record_id, actor, playable=True)
        if latest["version"] != doc["version"]:
            raise ConflictError("Recording changed during access. Refresh before playback.")
        await self.audit(actor.require_id(), "download" if download else "playback", record_id)
        return data

    async def save_transcript(
        self, record_id: str, payload: TranscriptInput, actor: User
    ) -> dict[str, Any]:
        doc = await self.get(record_id, actor, playable=True)
        if doc["version"] != payload.version:
            raise ConflictError("Recording changed. Refresh before importing transcript.")
        if any(segment.end_seconds > doc["duration_seconds"] for segment in payload.segments):
            raise ValidationError("Transcript timestamps exceed the verified audio duration.")
        # One atomic derivative in the recording avoids transcript+parent split commits.
        content = payload.model_dump(exclude={"version"})
        result = await self.repo.update(
            "voice_recordings",
            doc,
            {
                "transcript_status": "imported_unverified_recognition",
                "transcript_ciphertext": encrypt(json.dumps(content)),
                "transcript_imported_by": actor.require_id(),
                "transcript_imported_at": utc_now(),
            },
            actor.require_id(),
        )
        await self.audit(actor.require_id(), "transcript_imported", record_id)
        return {
            "version": result["version"],
            "status": result["transcript_status"],
            "provenance": "operator_supplied_recognition_not_independently_verified",
        }

    async def transcript(self, record_id: str, actor: User) -> dict[str, Any]:
        doc = await self.get(record_id, actor, playable=True)
        if not doc.get("transcript_ciphertext"):
            raise NotFoundError(
                "No recognized transcript has been imported; live transcription is blocked."
            )
        try:
            data = json.loads(decrypt(doc["transcript_ciphertext"]))
        except (ValueError, InvalidToken):
            raise ValidationError("Transcript is unavailable or failed decryption.") from None
        await self.audit(actor.require_id(), "transcript_viewed", record_id)
        return {
            **data,
            "recording_id": record_id,
            "provenance": "operator_supplied_recognition_not_independently_verified",
            "summary": None,
            "summary_status": "not_generated",
        }

    async def delete(self, record_id: str, actor: User, version: int) -> dict[str, Any]:
        doc = await self.get(record_id, actor)
        if version != doc["version"]:
            raise ConflictError("Recording changed. Refresh before deleting.")
        if doc["status"] == "pending" and doc["lease_until"] > utc_now():
            raise ConflictError("Import is still processing. Retry deletion after reconciliation.")
        if doc["status"] != "deleted":
            doc = await self.repo.update(
                "voice_recordings", doc, {"status": "deletion_pending"}, actor.require_id()
            )
            await self.remove_artifacts(doc, actor.require_id(), "operator_deleted")
        await self.audit(actor.require_id(), "deleted", record_id)
        return {"status": "deleted", "id": record_id}

    async def recover(self, record_id: str, actor: User, version: int) -> dict[str, Any]:
        doc = await self.get(record_id, actor)
        if doc["version"] != version:
            raise ConflictError("Recording changed. Refresh before recovery.")
        if doc["status"] not in {"pending", "failed"} or doc["expires_at"] <= utc_now():
            raise ForbiddenError("Only an unexpired interrupted/failed import can be recovered.")
        if doc["status"] == "pending" and doc["lease_until"] > utc_now():
            raise ConflictError("Import is still processing; wait for its lease to expire.")
        try:
            data = await asyncio.to_thread(self.storage.read, record_id, doc["sha256"])
            await asyncio.to_thread(validate_wav, data)
        except (OSError, ValueError, InvalidToken, ValidationError):
            raise ValidationError(
                "No valid stored artifact is available to recover. Import the authorized WAV with a new import key."
            ) from None
        result = await self.repo.update(
            "voice_recordings",
            doc,
            {
                "status": "completed",
                "verified_at": utc_now(),
                "recovered_at": utc_now(),
                "error": None,
            },
            actor.require_id(),
        )
        await self.audit(actor.require_id(), "recovered", record_id)
        return recording_public(result)

    async def remove_artifacts(self, doc: dict[str, Any], actor_id: str, reason: str) -> None:
        record_id = str(doc["_id"])
        try:
            await asyncio.to_thread(self.storage.delete, record_id)
        except (OSError, ValidationError):
            raise ValidationError(
                "Private artifact deletion failed; playback remains disabled and the retention worker will retry."
            ) from None
        result = await self.db.voice_recordings.update_one(
            {"_id": doc["_id"], "version": doc["version"]},
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": utc_now(),
                    "delete_reason": reason,
                    "transcript_status": "deleted",
                    "updated_at": utc_now(),
                    "updated_by": actor_id,
                },
                "$unset": {
                    "transcript_ciphertext": "",
                    "consent_reference": "",
                    "sha256": "",
                    "request_fingerprint": "",
                },
                "$inc": {"version": 1},
            },
        )
        if not result.matched_count:
            latest = await self.db.voice_recordings.find_one({"_id": doc["_id"]})
            if not latest or latest["status"] != "deleted":
                raise ConflictError(
                    "Recording changed during deletion; reconciliation is required."
                )

    async def reconcile(self) -> dict[str, int]:
        now = utc_now()
        processed = failed = 0
        query = {
            "is_deleted": False,
            "status": {"$ne": "deleted"},
            "$or": [
                {"expires_at": {"$lte": now}},
                {"status": "deletion_pending"},
                {"status": "pending", "lease_until": {"$lte": now}},
            ],
        }
        async for doc in self.db.voice_recordings.find(query).limit(100):
            try:
                if doc["expires_at"] <= now or doc["status"] == "deletion_pending":
                    if doc["status"] != "deletion_pending":
                        doc = await self.repo.update(
                            "voice_recordings", doc, {"status": "deletion_pending"}, "voice-worker"
                        )
                    await self.remove_artifacts(doc, "voice-worker", "retention_expired")
                else:
                    try:
                        data = await asyncio.to_thread(
                            self.storage.read, str(doc["_id"]), doc["sha256"]
                        )
                        await asyncio.to_thread(validate_wav, data)
                        updates = {"status": "completed", "verified_at": now, "recovered_at": now}
                    except (OSError, ValueError, InvalidToken, ValidationError):
                        updates = {
                            "status": "failed",
                            "error": "interrupted_import_without_verified_artifact",
                        }
                    await self.repo.update("voice_recordings", doc, updates, "voice-worker")
                await self.audit("voice-worker", "reconciled", str(doc["_id"]))
                processed += 1
            except ConflictError:
                continue
            except ValidationError:
                failed += 1
        await self.db.voice_worker_health.update_one(
            {"singleton_key": "recordings"},
            {"$set": {"heartbeat_at": now, "processed": processed, "failed": failed}},
            upsert=True,
        )
        return {"processed": processed, "failed": failed}
