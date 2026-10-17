"""Durable control plane. No production capability is inferred from configuration."""

import hashlib
import json
from datetime import timedelta
from typing import Any, cast

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.platform_schemas import (
    ActivationChange,
    Component,
    ComponentChange,
    Environment,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

COMPONENTS = (
    "telephony",
    "stt",
    "tts",
    "inference",
    "media",
    "workers",
    "recording",
    "transfer",
    "smartflo",
    "callbacks",
)
POLICY_VERSION = "native-live-v1"
UNIMPLEMENTED_TEST_COMPONENTS = {"media", "recording", "transfer"}


async def require_component_testing(
    db: AsyncIOMotorDatabase[Any], key: str, environment: Environment = "test"
) -> None:
    """Explicit central disable overrides existing operator-enabled test adapters.

    Preserve previously configured legacy test behavior until controls are first
    initialized; no legacy path can make live calls.
    """
    control = await db.voice_platform_controls.find_one({"environment": environment})
    if control and not control["components"][key]["enabled"]:
        raise ForbiddenError(f"{key} is disabled in {environment} platform controls.")


async def ensure_platform_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_platform_controls.create_index("environment", unique=True)


class PlatformService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def record(self, environment: Environment) -> dict[str, Any]:
        await self.db.voice_platform_controls.update_one(
            {"environment": environment},
            {
                "$setOnInsert": {
                    "environment": environment,
                    "version": 1,
                    "emergency_stopped": True,
                    "inbound": False,
                    "outbound": False,
                    "processing": False,
                    "components": {
                        key: {"enabled": False, "profile_id": None} for key in COMPONENTS
                    },
                    "history": [],
                    "policy_version": POLICY_VERSION,
                }
            },
            upsert=True,
        )
        result = await self.db.voice_platform_controls.find_one({"environment": environment})
        assert result is not None
        for key in COMPONENTS:
            result["components"].setdefault(key, {"enabled": False, "profile_id": None})
        return cast(dict[str, Any], result)

    async def readiness(self, doc: dict[str, Any]) -> list[dict[str, Any]]:
        # These gates have no trusted verifier yet. A DB flag or uploaded reference
        # must never turn a missing implementation into a live-capable adapter.
        descriptions = {
            "native_control_media": "Deployed PBX version, call control and bidirectional media require real verification.",
            "operator_number_routing": "Approved trunk, authorized numbers/caller ID and direction-specific routing required.",
            "speech_pipeline": "Approved STT/TTS models and actual end-to-end audio acceptance required.",
            "consent_compliance": "Verified consent, calling windows and approved compliance policy required.",
            "emergency_drain": "Active-call draining or independent human transfer requires implementation and testing.",
            "staging_acceptance": "Real authorized end-to-end and resource/concurrency acceptance required.",
            "customer_voice_identity": "Approved voice-session identity verification and authoritative customer-only tools require implementation and real testing.",
            "live_callback_safety": "Durable callback requests do not verify real dispatch, retries, contact reservations or customer opt-out handling on the live call path.",
        }
        gates = [
            {"key": key, "passed": False, "remediation": value}
            for key, value in descriptions.items()
        ]
        heartbeat = await self.db.voice_worker_health.find_one({"singleton_key": "default"})
        healthy = bool(
            heartbeat
            and heartbeat.get("heartbeat_at")
            and heartbeat["heartbeat_at"] > utc_now() - timedelta(seconds=30)
        )
        gates.append(
            {
                "key": "worker_heartbeat",
                "passed": healthy,
                "remediation": "Fresh existing ARQ heartbeat required; does not prove media capacity.",
            }
        )
        for key in ("telephony", "stt", "tts", "inference", "media", "workers"):
            gates.append(
                {
                    "key": f"component_{key}",
                    "passed": bool(doc["components"][key]["enabled"]),
                    "remediation": f"Enable and verify {key}; enablement alone is not a successful test.",
                }
            )
        from app.features.voice_assistant.speech_jobs import SpeechJobs

        speech_jobs = SpeechJobs(self.db)
        speech = await speech_jobs.summary(doc["environment"])
        for kind in ("stt", "tts"):
            gates.append(
                {
                    "key": f"functional_{kind}",
                    "passed": speech[kind] == "functional_test_passed",
                    "remediation": f"Run an actual local {kind.upper()} test with current configuration; evidence expires after 15 minutes.",
                }
            )
        pipeline = await self.db.voice_speech_jobs.find_one(
            {"environment": doc["environment"], "kind": "pipeline"}, sort=[("created_at", -1)]
        )
        pipeline_passed = bool(
            pipeline
            and pipeline["status"] == "passed"
            and pipeline.get("finished_at")
            and pipeline["finished_at"] > utc_now() - timedelta(minutes=15)
            and await speech_jobs.current(pipeline)
        )
        gates.append(
            {
                "key": "local_audio_pipeline",
                "passed": pipeline_passed,
                "remediation": "Current local STT → inference → TTS test required. This does not satisfy real PBX audio acceptance.",
            }
        )
        return gates

    async def status(self, environment: Environment, actor: User) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.record(environment)
        gates = await self.readiness(doc)
        token = hashlib.sha256(
            json.dumps(
                [environment, doc["version"], POLICY_VERSION, gates], sort_keys=True
            ).encode()
        ).hexdigest()
        result = {
            key: doc[key]
            for key in (
                "environment",
                "version",
                "emergency_stopped",
                "inbound",
                "outbound",
                "processing",
                "components",
                "history",
                "policy_version",
            )
        } | {
            "gates": gates,
            "evidence_token": token,
            "production_eligible": all(g["passed"] for g in gates),
            "live_implementation_available": False,
        }
        result["components"] = {
            key: value | {"testing_supported": key not in UNIMPLEMENTED_TEST_COMPONENTS}
            for key, value in doc["components"].items()
        }
        return result

    async def change(
        self,
        environment: Environment,
        version: int,
        fields: dict[str, Any],
        actor: User,
        event: str,
        reason: str,
    ) -> None:
        entry = {
            "event": event,
            "reason": reason,
            "actor_id": actor.require_id(),
            "at": utc_now(),
            "policy_version": POLICY_VERSION,
        }
        result = await self.db.voice_platform_controls.find_one_and_update(
            {"environment": environment, "version": version},
            {
                "$set": fields,
                "$inc": {"version": 1},
                "$push": {"history": {"$each": [entry], "$slice": -200}},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise ConflictError("Voice controls changed. Refresh and review the current evidence.")
        await write_audit_log(
            self.db,
            event_type="voice_assistant.platform_control_changed",
            user_id=actor.require_id(),
            metadata={
                "environment": environment,
                "action": event,
                "control_version": version + 1,
                "policy_version": POLICY_VERSION,
            },
        )

    async def component(
        self, environment: Environment, key: Component, payload: ComponentChange, actor: User
    ) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.record(environment)
        if doc["version"] != payload.version:
            raise ConflictError("Voice controls changed. Refresh before changing components.")
        if payload.enabled and key in UNIMPLEMENTED_TEST_COMPONENTS:
            raise ForbiddenError(
                "This live subsystem has no installed runtime; enablement is unavailable."
            )
        if payload.profile_id is not None:
            from app.features.voice_assistant.speech_runtime import get_speech_config

            profile = get_speech_config().profiles.get(payload.profile_id)
            if key not in {"stt", "tts"} or profile is None or profile.kind != key:
                raise ForbiddenError("Select a server-approved speech profile for this component.")
        # Reconfiguration invalidates all live directions atomically. Enable is a
        # permission for testing only, never an installation/health assertion.
        await self.change(
            environment,
            payload.version,
            {
                f"components.{key}": {"enabled": payload.enabled, "profile_id": payload.profile_id},
                "inbound": False,
                "outbound": False,
                "processing": False,
                "emergency_stopped": True,
            },
            actor,
            f"component.{key}.{'enabled_for_testing' if payload.enabled else 'disabled'}",
            payload.reason,
        )
        return await self.status(environment, actor)

    async def activation(
        self, environment: Environment, payload: ActivationChange, actor: User
    ) -> dict[str, Any]:
        owner_only(actor)
        state = await self.status(environment, actor)
        if state["version"] != payload.version:
            raise ConflictError("Voice controls changed. Refresh before changing activation.")
        if payload.enabled:
            if payload.confirmation != "ENABLE LIVE CALLING":
                raise ForbiddenError("Explicit Owner confirmation is required.")
            # Fail closed even if database documents or a client are tampered with.
            # There is no supported live runtime, so no positive activation branch.
            await write_audit_log(
                self.db,
                event_type="voice_assistant.platform_activation_denied",
                user_id=actor.require_id(),
                metadata={
                    "environment": environment,
                    "direction": payload.direction,
                    "policy_version": POLICY_VERSION,
                },
            )
            raise ForbiddenError(
                "Live activation blocked: actual media, telecom, speech and acceptance prerequisites remain unverified.",
                details={"gates": state["gates"]},
            )
        await self.change(
            environment,
            payload.version,
            {payload.direction: False},
            actor,
            f"{payload.direction}.disabled",
            payload.reason,
        )
        return await self.status(environment, actor)

    async def emergency(self, environment: Environment, actor: User, reason: str) -> dict[str, Any]:
        owner_only(actor)
        await self.record(environment)
        # No stale-version requirement: an emergency stop must win over old UI state.
        await self.db.voice_platform_controls.update_one(
            {"environment": environment},
            {
                "$set": {
                    "inbound": False,
                    "outbound": False,
                    "processing": False,
                    "emergency_stopped": True,
                },
                "$inc": {"version": 1},
                "$push": {
                    "history": {
                        "$each": [
                            {
                                "event": "emergency.disabled",
                                "actor_id": actor.require_id(),
                                "reason": reason,
                                "at": utc_now(),
                                "policy_version": POLICY_VERSION,
                            }
                        ],
                        "$slice": -200,
                    }
                },
            },
        )
        await write_audit_log(
            self.db,
            event_type="voice_assistant.platform_emergency_disabled",
            user_id=actor.require_id(),
            metadata={"environment": environment, "policy_version": POLICY_VERSION},
        )
        return await self.status(environment, actor)

    async def require_live(self, environment: Environment, direction: str) -> None:
        # Mandatory future call-entry guard. Do not issue any call command upstream
        # until a genuine supported runtime replaces this explicit fail-closed gate.
        raise ForbiddenError("Live runtime unavailable; no call may be started.")
