"""Owner-only configuration and local evidence. No live provider authorization."""

import json
from typing import Any

from cryptography.fernet import InvalidToken
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config.settings import get_settings
from app.core.exceptions import ConflictError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.airtel_auth import signed_headers
from app.features.voice_assistant.airtel_config import AirtelConnectionInput
from app.features.voice_assistant.airtel_media import AirtelMediaSession
from app.features.voice_assistant.airtel_rest import C2C_PATH, ORIGIN, RECORDING_PATH
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

PROVIDER = "airtel_iq_voice"


class AirtelVoiceService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    async def document(self) -> dict[str, Any]:
        return dict(
            await self.db.voice_provider_connections.find_one({"provider": PROVIDER})
            or {"provider": PROVIDER, "version": 1}
        )

    async def status(self, actor: User) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.document()
        root = (
            f"{doc['public_origin']}{get_settings().api_v1_prefix}/voice-assistant/airtel"
            if doc.get("public_origin")
            else None
        )
        return {
            "provider": PROVIDER,
            "version": doc["version"],
            **{
                k: doc.get(k)
                for k in ("public_origin", "account_sid", "caller_id", "call_flow_id", "last_test")
            },
            "requested_concurrency": doc.get("requested_concurrency", 500),
            "credentials_configured": bool(doc.get("credentials_encrypted")),
            "recording_api_origin": ORIGIN,
            "c2c_path": C2C_PATH,
            "recording_path": RECORDING_PATH,
            "c2c_origin_status": "requires_account_confirmation",
            "live_calling": False,
            "provider_authentication": "not_verified",
            "connection_status": "configuration_saved"
            if doc.get("credentials_encrypted")
            else "not_configured",
            "webhook_status": "blocked_pending_authentication_and_correlation_contract",
            "audio_status": "offline_protocol_only",
            "capacity_status": "not_measured",
            "media_url": root.replace("https://", "wss://") + "/media" if root else None,
            "events_url": root + "/webhooks/events" if root else None,
            "cdr_url": root + "/webhooks/cdr" if root else None,
            "url_verification": "not_externally_verified_do_not_register",
            "blockers": [
                "No approved Airtel account, C2C origin/response contract or call-flow topology verified.",
                "WSS/callback authentication and provider IP ranges require bilateral onboarding.",
                "Callback field variants and stable event/CDR correlation require confirmation.",
                "Live speech services, media hosting and server capacity are not verified.",
                "Human-to-AI return on the same customer call is not documented in this guide.",
            ],
        }

    async def save(self, payload: AirtelConnectionInput, actor: User) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.document()
        if payload.version != doc["version"]:
            raise ConflictError("Airtel VoiceBOT settings changed. Reload before saving.")
        credentials = doc.get("credentials_encrypted")
        if payload.app_id and payload.api_key:
            credentials = encrypt(
                json.dumps(
                    {
                        "app_id": payload.app_id.get_secret_value(),
                        "api_key": payload.api_key.get_secret_value(),
                    }
                )
            )
        if payload.clear_credentials:
            credentials = None
        updates = {
            k: getattr(payload, k)
            for k in (
                "public_origin",
                "account_sid",
                "caller_id",
                "call_flow_id",
                "requested_concurrency",
            )
        }
        updates.update(
            provider=PROVIDER,
            version=payload.version + 1,
            credentials_encrypted=credentials,
            last_test=None,
            updated_at=utc_now(),
            updated_by=actor.require_id(),
        )
        try:
            result = await self.db.voice_provider_connections.find_one_and_update(
                {"provider": PROVIDER, "version": payload.version},
                {"$set": updates},
                upsert=payload.version == 1,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            raise ConflictError("Airtel VoiceBOT settings changed. Reload before saving.") from None
        if result is None:
            raise ConflictError("Airtel VoiceBOT settings changed. Reload before saving.")
        await write_audit_log(
            self.db,
            event_type="voice_assistant.airtel_settings_saved",
            user_id=actor.require_id(),
            metadata={"configuration_version": updates["version"]},
        )
        return await self.status(actor)

    async def validate(self, actor: User) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.document()
        if not doc.get("credentials_encrypted"):
            raise ValidationError(
                "Save Airtel VoiceBOT credentials first. No provider request was sent."
            )
        try:
            creds = json.loads(decrypt(doc["credentials_encrypted"]))
            signed_headers(creds["app_id"], creds["api_key"], b"{}", at=utc_now())
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise ValidationError(
                "Stored credentials are unavailable or invalid. Replace both credentials."
            ) from None
        # Exercise the real codec without claiming reachability or live audio.
        codec = AirtelMediaSession(account_sid="local-test")
        codec.ingest('{"event":"connected","protocol":"Call","version":"1.0.0"}')
        codec.ingest(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "local-stream",
                    "start": {
                        "streamSid": "local-stream",
                        "accountSid": "local-test",
                        "callSid": "local-call",
                        "callerNumber": "919000000001",
                        "calledNumber": "919000000002",
                        "mediaFormat": {"encoding": "ulaw", "sampleRate": "8000", "channels": "1"},
                    },
                }
            )
        )
        if codec.ingest(json.dumps(codec.output(audio=b"\xff" * 160)))["audio"] != b"\xff" * 160:
            raise ValidationError("Local codec validation failed; live calling remains disabled.")
        evidence = {
            "status": "local_contract_passed",
            "scope": "offline_signing_and_codec_only",
            "configuration_version": doc["version"],
            "checked_at": utc_now(),
            "provider_verified": False,
            "calls_placed": 0,
            "message": "Signing and offline codec passed. API authentication, webhook reachability and live audio remain unverified; no network request was sent.",
        }
        result = await self.db.voice_provider_connections.update_one(
            {"provider": PROVIDER, "version": doc["version"]}, {"$set": {"last_test": evidence}}
        )
        if result.matched_count != 1:
            raise ConflictError(
                "Configuration changed during validation. Repeat against current settings."
            )
        await write_audit_log(
            self.db,
            event_type="voice_assistant.airtel_local_validation",
            user_id=actor.require_id(),
            metadata={"configuration_version": doc["version"], "calls_placed": 0},
        )
        return evidence
