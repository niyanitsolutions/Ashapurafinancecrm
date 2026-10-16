"""Durable local verification queue, polled by existing ARQ. No calls or downloads."""

import asyncio
import base64
import hashlib
import json
import time
from datetime import timedelta
from typing import Any

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.conversation import (
    LocalConversationAdapter,
    get_conversation_config,
)
from app.features.voice_assistant.local_pipeline import LocalUtterancePipeline
from app.features.voice_assistant.platform_schemas import Environment
from app.features.voice_assistant.platform_service import PlatformService
from app.features.voice_assistant.speech_runtime import (
    LocalSpeechRuntime,
    asset,
    get_speech_config,
    verify,
)
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


def configuration_key(profile_id: str) -> str:
    cfg = get_speech_config()
    profile = cfg.profiles.get(profile_id)
    return hashlib.sha256(
        json.dumps(
            [
                cfg.root,
                cfg.timeout_seconds,
                cfg.threads,
                cfg.memory_limit_mb,
                profile.model_dump() if profile else None,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def inference_fingerprint() -> str:
    return hashlib.sha256(get_conversation_config().model_dump_json().encode()).hexdigest()


async def ensure_speech_job_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_speech_jobs.create_index([("environment", 1), ("created_at", -1)])
    await db.voice_speech_jobs.create_index("expires_at", expireAfterSeconds=0)


def safe_job(doc: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(doc["_id"])} | {
        key: doc.get(key)
        for key in (
            "environment",
            "profile_id",
            "kind",
            "status",
            "created_at",
            "finished_at",
            "expires_at",
            "diagnostic",
            "latency_ms",
            "evidence",
            "control_version",
        )
    }


class SpeechJobs:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def summary(self, environment: Environment) -> dict[str, str]:
        profiles = get_speech_config().profiles
        control = await self.db.voice_platform_controls.find_one({"environment": environment})
        result = {}
        for kind in ("stt", "tts"):
            if not any(profile.kind == kind for profile in profiles.values()):
                result[kind] = "not_installed"
                continue
            component = (control or {}).get("components", {}).get(kind) or {}
            if not component.get("enabled"):
                result[kind] = "disabled"
                continue
            job = await self.db.voice_speech_jobs.find_one(
                {
                    "environment": environment,
                    "profile_id": component.get("profile_id"),
                    "kind": kind,
                    "expires_at": {"$gt": utc_now()},
                },
                sort=[("created_at", -1)],
            )
            result[kind] = "configured_not_tested"
            if (
                job
                and job["status"] == "passed"
                and await self.current(job)
                and job.get("finished_at")
                and job["finished_at"] > utc_now() - timedelta(minutes=15)
            ):
                result[kind] = "functional_test_passed"
            elif job and job["status"] in {"failed", "interrupted", "expired"}:
                result[kind] = "test_failed"
        return result

    async def catalog(self, actor: User) -> dict[str, Any]:
        owner_only(actor)
        profiles = get_speech_config().profiles
        return {
            "profiles": [
                {
                    "id": key,
                    "kind": profile.kind,
                    "engine": profile.engine,
                    "language": profile.language,
                    "version": profile.version,
                    "state": "configured_not_tested",
                    "installation": "operator_managed",
                    "license_review_required": True,
                }
                for key, profile in profiles.items()
            ],
            "message": "Profiles are server-approved configuration, not installed or verified health. Install pinned runtimes/models through the reviewed deployment procedure; no automatic downloads.",
        }

    async def submit(
        self, environment: Environment, profile_id: str, actor: User, *, pipeline: bool = False
    ) -> dict[str, Any]:
        owner_only(actor)
        cfg = get_speech_config()
        control = await PlatformService(self.db).record(environment)
        if pipeline:
            profile_id = control["components"]["stt"]["profile_id"] or ""
            if not control["components"]["inference"]["enabled"]:
                raise ForbiddenError("Enable local inference testing first.")
        profile = cfg.profiles.get(profile_id)
        if profile is None:
            raise NotFoundError("Server-approved speech profile not found.")
        component = control["components"][profile.kind]
        if (
            not component["enabled"]
            or component["profile_id"] != profile_id
            or not control["components"]["workers"]["enabled"]
        ):
            raise ForbiddenError(
                "Select and enable this speech profile and voice verification workers for testing first."
            )
        tts_profile = None
        if pipeline:
            tts_profile = control["components"]["tts"]["profile_id"]
            tts = cfg.profiles.get(tts_profile or "")
            ai = get_conversation_config()
            if (
                not tts
                or tts.kind != "tts"
                or not control["components"]["tts"]["enabled"]
                or not ai.local_ai_enabled
                or not ai.local_ai_model
                or tts.language != profile.language
            ):
                raise ForbiddenError(
                    "Approved matching-language STT/TTS and configured local inference are required."
                )
        now = utc_now()
        if (
            await self.db.voice_speech_jobs.count_documents(
                {"status": {"$in": ["queued", "running"]}, "expires_at": {"$gt": now}}
            )
            >= 10
        ):
            raise ConflictError(
                "Local speech verification queue is full. Retry after a job finishes."
            )
        # Burst admission is bounded atomically by a fixed set of ten queue slots.
        slot = None
        slot_token = str(ObjectId())
        for number in range(10):
            try:
                result = await self.db.voice_speech_slots.find_one_and_update(
                    {
                        "_id": f"speech-test-{number}",
                        "$or": [{"until": {"$lte": now}}, {"until": {"$exists": False}}],
                    },
                    {"$set": {"until": now + timedelta(minutes=15), "token": slot_token}},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                if result:
                    slot = f"speech-test-{number}"
                    break
            except DuplicateKeyError:
                continue
        if slot is None:
            raise ConflictError("Local speech verification queue is full.")
        document: dict[str, Any] = {
            "environment": environment,
            "profile_id": profile_id,
            "kind": profile.kind,
            "status": "queued",
            "created_at": now,
            "expires_at": now + timedelta(hours=1),
            "queue_deadline": now + timedelta(minutes=5),
            "actor_id": actor.require_id(),
            "control_version": control["version"],
            "configuration_key": configuration_key(profile_id),
            "slot": slot,
            "slot_token": slot_token,
        }
        if pipeline and tts_profile:
            document.update(
                {
                    "kind": "pipeline",
                    "tts_profile": tts_profile,
                    "tts_configuration_key": configuration_key(tts_profile),
                    "inference_configuration_key": inference_fingerprint(),
                }
            )
        try:
            result = await self.db.voice_speech_jobs.insert_one(document)
        except Exception:
            await self.db.voice_speech_slots.update_one(
                {"_id": slot, "token": slot_token}, {"$set": {"until": now}}
            )
            raise
        document["_id"] = result.inserted_id
        await write_audit_log(
            self.db,
            event_type="voice_assistant.speech_test_requested",
            user_id=actor.require_id(),
            metadata={
                "job_id": str(result.inserted_id),
                "environment": environment,
                "kind": document["kind"],
            },
        )
        return safe_job(document)

    async def list(self, environment: Environment, actor: User, page: int = 1) -> dict[str, Any]:
        owner_only(actor)
        query = {"environment": environment, "expires_at": {"$gt": utc_now()}}
        docs = (
            await self.db.voice_speech_jobs.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {
            "items": [safe_job(doc) for doc in docs],
            "total": await self.db.voice_speech_jobs.count_documents(query),
        }

    async def audio(self, environment: Environment, record_id: str, actor: User) -> bytes:
        owner_only(actor)
        if not ObjectId.is_valid(record_id):
            raise NotFoundError("Speech test audio not found.")
        doc = await self.db.voice_speech_jobs.find_one(
            {
                "_id": ObjectId(record_id),
                "environment": environment,
                "status": "passed",
                "expires_at": {"$gt": utc_now()},
            }
        )
        if not doc or not doc.get("audio_encrypted"):
            raise NotFoundError("Speech test audio unavailable or expired.")
        return base64.b64decode(decrypt(doc["audio_encrypted"]), validate=True)

    async def sweep(self) -> int:
        now = utc_now()
        cfg = get_speech_config()
        # One global CPU-heavy verification at a time across processes/environments.
        token = str(ObjectId())
        try:
            lease = await self.db.voice_runtime_leases.find_one_and_update(
                {
                    "_id": "speech-test",
                    "$or": [{"until": {"$lte": now}}, {"until": {"$exists": False}}],
                },
                {"$set": {"token": token, "until": now + timedelta(seconds=360)}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return 0
        if not lease:
            return 0
        try:
            # A worker lost its lease or queued work expired: never silently retry.
            abandoned = (
                await self.db.voice_speech_jobs.find({"status": "running"}).limit(10).to_list(10)
            )
            expired = (
                await self.db.voice_speech_jobs.find(
                    {"status": "queued", "queue_deadline": {"$lte": now}}
                )
                .limit(10)
                .to_list(10)
            )
            await self.db.voice_speech_jobs.update_many(
                {"status": "running"},
                {
                    "$set": {
                        "status": "interrupted",
                        "finished_at": now,
                        "diagnostic": "Worker interrupted; request a new explicit test.",
                    }
                },
            )
            await self.db.voice_speech_jobs.update_many(
                {"status": "queued", "queue_deadline": {"$lte": now}},
                {
                    "$set": {
                        "status": "expired",
                        "finished_at": now,
                        "diagnostic": "Verification queue deadline expired.",
                    }
                },
            )
            for abandoned_job in [*abandoned, *expired]:
                await self.db.voice_speech_slots.update_one(
                    {"_id": abandoned_job["slot"], "token": abandoned_job["slot_token"]},
                    {"$set": {"until": now}},
                )
            job = await self.db.voice_speech_jobs.find_one_and_update(
                {"status": "queued", "queue_deadline": {"$gt": now}},
                {"$set": {"status": "running", "lease_token": token, "started_at": now}},
                sort=[("created_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if not job:
                return 0
            started = time.perf_counter()
            result: dict[str, Any] = {
                "status": "failed",
                "diagnostic": "Local speech verification failed. Check approved assets, runtime compatibility and isolated worker limits.",
            }
            try:
                audio: bytes | None
                if not await self.current(job):
                    raise ValueError("Configuration changed or component disabled.")
                if job["kind"] == "pipeline":
                    profile = cfg.profiles[job["profile_id"]]
                    assert profile.sample and profile.sample_sha256
                    sample = asset(cfg.root, profile.sample)
                    await asyncio.to_thread(verify, sample, profile.sample_sha256)
                    if sample.stat().st_size > 1_000_000:
                        raise ValueError("Reference audio exceeded budget.")
                    audio, evidence = await LocalUtterancePipeline(
                        LocalSpeechRuntime(cfg), LocalConversationAdapter()
                    ).respond(
                        audio=sample.read_bytes(),
                        stt_profile=job["profile_id"],
                        tts_profile=job["tts_profile"],
                        sources=[],
                        instructions="Synthetic local audio verification. Identify as an AI assistant. Acknowledge uncertainty and offer human assistance without sources.",
                        operational_rules="No financial decisions, customer data or tools. No real call.",
                        language=profile.language,
                        authorize=lambda: self.current(job),
                    )
                else:
                    evidence, audio = await LocalSpeechRuntime(cfg).test(job["profile_id"])
                if not await self.current(job):
                    result = {
                        "status": "superseded",
                        "diagnostic": "Configuration changed during verification; evidence discarded.",
                    }
                else:
                    result = {
                        "status": "passed",
                        "diagnostic": "Actual local speech request completed; live calling and language quality remain unverified.",
                        "evidence": evidence,
                    }
                    if audio:
                        result["audio_encrypted"] = encrypt(base64.b64encode(audio).decode("ascii"))
            except (
                OSError,
                ValueError,
                TimeoutError,
                EOFError,
                httpx.HTTPError,
                KeyError,
                TypeError,
            ):
                pass
            result |= {
                "finished_at": utc_now(),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
            await self.db.voice_speech_jobs.update_one(
                {"_id": job["_id"], "status": "running", "lease_token": token}, {"$set": result}
            )
            await write_audit_log(
                self.db,
                event_type="voice_assistant.speech_test_finished",
                user_id=job["actor_id"],
                metadata={
                    "job_id": str(job["_id"]),
                    "environment": job["environment"],
                    "status": result["status"],
                },
            )
            await self.db.voice_speech_slots.update_one(
                {"_id": job["slot"], "token": job["slot_token"]}, {"$set": {"until": now}}
            )
            return 1
        finally:
            await self.db.voice_runtime_leases.update_one(
                {"_id": "speech-test", "token": token}, {"$set": {"until": utc_now()}}
            )

    async def current(self, job: dict[str, Any]) -> bool:
        control = await PlatformService(self.db).record(job["environment"])
        component = control["components"]["stt" if job["kind"] == "pipeline" else job["kind"]]
        if job["kind"] == "pipeline":
            tts = control["components"]["tts"]
            if not (
                tts["enabled"]
                and tts["profile_id"] == job["tts_profile"]
                and control["components"]["inference"]["enabled"]
                and configuration_key(job["tts_profile"]) == job["tts_configuration_key"]
                and inference_fingerprint() == job["inference_configuration_key"]
            ):
                return False
        return bool(
            control["version"] == job["control_version"]
            and component["enabled"]
            and component["profile_id"] == job["profile_id"]
            and control["components"]["workers"]["enabled"]
            and configuration_key(job["profile_id"]) == job["configuration_key"]
        )
