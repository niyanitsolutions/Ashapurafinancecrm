"""Functional text-inference evidence, independent of PBX/provider readiness."""

import hashlib
import json
import time
from datetime import timedelta
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.conversation import (
    LocalConversationAdapter,
    get_conversation_config,
)
from app.features.voice_assistant.platform_service import require_component_testing
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def ensure_ai_health_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_ai_health.create_index("config_fingerprint", unique=True)
    await db.voice_ai_health.create_index("checked_at", expireAfterSeconds=30 * 86400)


def fingerprint() -> str:
    config = get_conversation_config()
    return hashlib.sha256(
        json.dumps([config.local_ai_url, config.local_ai_model, config.local_ai_enabled]).encode()
    ).hexdigest()


class SelfHostedHealthService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def status(self, actor: User) -> dict[str, Any]:
        owner_only(actor)
        config = get_conversation_config()
        control = await self.db.voice_platform_controls.find_one({"environment": "test"})
        control_version = control["version"] if control else 0
        permitted = not control or control["components"]["inference"]["enabled"]
        evidence = await self.db.voice_ai_health.find_one({"config_fingerprint": fingerprint()})
        fresh = bool(
            evidence
            and evidence.get("control_version", 0) == control_version
            and evidence["checked_at"] > utc_now() - timedelta(minutes=15)
        )
        from app.features.voice_assistant.speech_jobs import SpeechJobs

        speech = await SpeechJobs(self.db).summary("test")
        return {
            "text_inference": "disabled"
            if not config.local_ai_enabled or not permitted
            else "configuration_incomplete"
            if not config.local_ai_model
            else "functional_request_passed"
            if fresh and evidence and evidence["status"] == "functional_request_passed"
            else "unverified_or_unavailable",
            "model": config.local_ai_model or None,
            "configured": bool(config.local_ai_enabled and config.local_ai_model and permitted),
            "last_test": {
                key: evidence.get(key) for key in ("status", "checked_at", "latency_ms", "scope")
            }
            if evidence
            else None,
            "evidence_fresh": fresh,
            "speech_to_text": speech["stt"],
            "text_to_speech": speech["tts"],
            "live_calling": False,
            "language_quality_verified": False,
            "message": "Text inference checks do not validate speech, financial accuracy, tools, audio latency or live calls.",
        }

    async def test(self, actor: User) -> dict[str, Any]:
        owner_only(actor)
        await require_component_testing(self.db, "inference")
        config = get_conversation_config()
        if not config.local_ai_enabled or not config.local_ai_model:
            return await self.status(actor)
        key = fingerprint()
        control = await self.db.voice_platform_controls.find_one({"environment": "test"})
        control_version = control["version"] if control else 0
        started = time.perf_counter()
        try:
            await LocalConversationAdapter(config).respond(
                question="This is a synthetic readiness check. Acknowledge the check without financial or customer information.",
                history=[],
                sources=[],
                instructions="Respond briefly and acknowledge uncertainty without evidence.",
                operational_rules="Readiness check only. No tools or personal data.",
                language="en",
            )
            result = "functional_request_passed"
        except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
            result = "functional_request_failed"
        await self.db.voice_ai_health.update_one(
            {"config_fingerprint": key},
            {
                "$set": {
                    "checked_at": utc_now(),
                    "status": result,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "scope": "synthetic_structured_text_request_only",
                    "control_version": control_version,
                }
            },
            upsert=True,
        )
        await write_audit_log(
            self.db,
            event_type="voice_assistant.self_hosted_text_test",
            user_id=actor.require_id(),
            metadata={"status": result},
        )
        return await self.status(actor)
