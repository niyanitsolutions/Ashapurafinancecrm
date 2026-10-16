import asyncio
import hashlib
import json
import secrets
from datetime import UTC, timedelta
from typing import Any

import httpx
from cryptography.fernet import InvalidToken
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config.settings import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.smartflo_config import (
    API_ORIGIN,
    CALLBACK_EVENTS,
    SmartfloConnectionInput,
    SmartfloWebhookInput,
)
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


async def ensure_smartflo_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_provider_connections.create_index("provider", unique=True)
    await db.voice_provider_events.create_index("dedupe_key", unique=True)
    await db.voice_provider_events.create_index("expires_at", expireAfterSeconds=0)
    await db.voice_provider_events.create_index([("provider", 1), ("received_at", -1)])


class SmartfloService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]):
        self.db = db

    async def document(self) -> dict[str, Any]:
        doc = await self.db.voice_provider_connections.find_one({"provider": "smartflo"})
        return (
            dict(doc)
            if doc
            else {"provider": "smartflo", "version": 1, "callback_mode": "disabled"}
        )

    async def audit(self, actor: User, event: str) -> None:
        await write_audit_log(
            self.db, event_type=f"voice_assistant.smartflo_{event}", user_id=actor.require_id()
        )

    async def status(self) -> dict[str, Any]:
        doc = await self.document()
        origin = doc.get("public_origin")
        root = (
            f"{origin}{get_settings().api_v1_prefix}/voice-assistant/smartflo" if origin else None
        )
        last_test = doc.get("last_test")
        expired = bool(doc.get("token_expires_at") and doc["token_expires_at"] <= utc_now())
        connection_status = "not_configured"
        if doc.get("api_token_encrypted"):
            connection_status = (
                "expired" if expired else last_test["status"] if last_test else "not_tested"
            )
            if (
                last_test
                and not expired
                and utc_now() - last_test["tested_at"] > timedelta(minutes=30)
            ):
                connection_status = "verification_stale"
        return {
            "provider": "smartflo",
            "provider_name": "Tata Tele Business — Smartflo",
            "version": doc["version"],
            "api_base_url": API_ORIGIN,
            "public_origin": origin,
            "api_token_configured": bool(doc.get("api_token_encrypted")),
            "callback_token_configured": bool(doc.get("callback_token_encrypted")),
            "token_expires_at": doc.get("token_expires_at"),
            "token_expired": expired,
            "callback_mode": doc.get("callback_mode", "disabled"),
            "connection_status": connection_status,
            "last_test": last_test,
            "sandbox": "pending_provider_verification",
            "live_calling": False,
            "audio_status": "blocked_missing_speech_engine",
            "url_verification": "not_externally_verified",
            "incoming_webhook_url": f"{root}/webhooks/incoming" if root else None,
            "answered_webhook_url": f"{root}/webhooks/answered" if root else None,
            "call_status_webhook_url": f"{root}/webhooks/hangup" if root else None,
            "dynamic_endpoint_url": f"{root}/stream/resolve" if root else None,
            "audio_websocket_url": f"{root.replace('https://', 'wss://')}/media" if root else None,
            "documented_triggers": CALLBACK_EVENTS,
            "warnings": [
                "API verification covers only GET /v1/users; calling and voice-bot entitlements remain unverified.",
                "Callback header delivery must be verified in Smartflo's account request preview; no HMAC scheme is assumed.",
                "Validation callbacks are retained as observations and never start or control calls.",
                "Do not register the audio resolver while the speech engine is unavailable.",
            ],
        }

    async def save(self, payload: SmartfloConnectionInput, actor: User) -> dict[str, Any]:
        doc = await self.document()
        if payload.version != doc["version"]:
            raise ConflictError("Provider settings changed. Reload before saving.")
        token = doc.get("api_token_encrypted")
        callback = doc.get("callback_token_encrypted")
        if payload.api_token:
            token = encrypt(payload.api_token.get_secret_value())
        if payload.callback_token:
            callback = encrypt(payload.callback_token.get_secret_value())
        if payload.clear_api_token:
            token = None
        if payload.clear_callback_token:
            callback = None
        if token and callback and (payload.api_token or payload.callback_token):
            try:
                same = secrets.compare_digest(decrypt(token), decrypt(callback))
            except InvalidToken as exc:
                raise ValidationError(
                    "Stored credentials cannot be decrypted. Replace both tokens after checking the encryption key."
                ) from exc
            if same:
                raise ValidationError("API and callback tokens must be different.")
        if payload.callback_mode == "validation_only" and (
            not callback or not payload.public_origin
        ):
            raise ValidationError(
                "Validation callbacks require a public HTTPS origin and a separate callback token."
            )
        updates = {
            "provider": "smartflo",
            "version": payload.version + 1,
            "public_origin": payload.public_origin,
            "api_token_encrypted": token,
            "callback_token_encrypted": callback,
            "callback_mode": payload.callback_mode,
            "token_expires_at": payload.token_expires_at,
            "last_test": None,
            "updated_at": utc_now(),
            "updated_by": actor.require_id(),
        }
        try:
            result = await self.db.voice_provider_connections.find_one_and_update(
                {"provider": "smartflo", "version": payload.version},
                {"$set": updates},
                upsert=payload.version == 1,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ConflictError("Provider settings changed. Reload before saving.") from exc
        if result is None:
            raise ConflictError("Provider settings changed. Reload before saving.")
        await self.audit(actor, "settings_saved")
        return await self.status()

    async def test_connection(self, actor: User) -> dict[str, Any]:
        from app.features.voice_assistant.platform_service import require_component_testing

        await require_component_testing(self.db, "smartflo")
        doc = await self.document()
        ciphertext = doc.get("api_token_encrypted")
        if not ciphertext:
            raise ValidationError("Save a server-side Smartflo API token before testing.")
        if doc.get("token_expires_at") and doc["token_expires_at"] <= utc_now():
            raise ValidationError("The configured token expiry has passed. Replace the token.")
        status, message = (
            "failed",
            "Smartflo authentication or read-only scope could not be verified.",
        )
        code = None
        try:
            token = decrypt(ciphertext)
            body = bytearray()
            async with (
                asyncio.timeout(10),
                httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client,
                client.stream(
                    "GET",
                    f"{API_ORIGIN}/v1/users",
                    params={"limit": 1},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                ) as response,
            ):
                code = response.status_code
                if code == 200:
                    async for part in response.aiter_bytes(chunk_size=4096):
                        body.extend(part)
                        if len(body) > 65536:
                            raise ValueError("Response size limit exceeded.")
            if code == 200:
                data = json.loads(body)
                if (
                    isinstance(data, dict)
                    and isinstance(data.get("data"), list)
                    and data.get("success") is not False
                ):
                    status, message = (
                        "readonly_verified",
                        "Authentication and Users read scope verified. Live calling remains disabled.",
                    )
                else:
                    message = (
                        "Smartflo returned an unexpected response; connection remains unverified."
                    )
            elif code in {401, 403}:
                message = "Token rejected or Users scope/IP access denied. Check Smartflo token permissions and expiry."
            elif code == 429:
                message = (
                    "Smartflo rate limit reached. Retry later; no automatic retries were sent."
                )
            else:
                message = "Smartflo returned an unavailable or unsupported response. No provider payload was retained."
        except InvalidToken:
            message = "Stored API credentials cannot be decrypted. Re-enter the token after checking the backend encryption key."
        except (httpx.HTTPError, ValueError, TimeoutError):
            message = "Smartflo request failed or returned invalid/oversized JSON. Check connectivity and retry later."
        result = {"status": status, "message": message, "http_status": code, "tested_at": utc_now()}
        changed = await self.db.voice_provider_connections.update_one(
            {"provider": "smartflo", "version": doc["version"]},
            {"$set": {"last_test": result}},
        )
        if changed.matched_count != 1:
            raise ConflictError(
                "Credentials changed during the test. Test the current configuration again."
            )
        await self.audit(actor, "connection_test")
        return result

    async def authenticate_callback(self, authorization: str | None) -> None:
        doc = await self.document()
        secret = doc.get("callback_token_encrypted")
        if not secret:
            raise UnauthorizedError("Smartflo callback authentication is not configured.")
        try:
            expected = f"Bearer {decrypt(secret)}".encode()
        except InvalidToken as exc:
            raise UnauthorizedError(
                "Callback credentials require administrator reconfiguration."
            ) from exc
        if not secrets.compare_digest((authorization or "").encode(), expected):
            raise UnauthorizedError("Smartflo callback authentication failed.")
        if doc.get("callback_mode") != "validation_only":
            raise ForbiddenError("Smartflo callback ingestion is disabled.")

    async def ingest(
        self, channel: str, payload: SmartfloWebhookInput, *, test: bool = False
    ) -> dict[str, Any]:
        if channel not in CALLBACK_EVENTS:
            raise ValidationError("Unsupported configured callback channel.")
        if channel == "hangup" and payload.call_status is None:
            raise ValidationError("Map the documented call_status variable for hangup callbacks.")
        stamp = payload.start_stamp.astimezone(UTC)
        normalized = {
            "uuid": payload.uuid,
            "start_stamp": stamp.isoformat(),
            "call_status": payload.call_status,
            "channel": channel,
            "test": test,
        }
        key = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
        now = utc_now()
        # No telephone numbers, recording URLs, raw bodies, tokens or transcripts are stored.
        doc = {
            "provider": "smartflo",
            "dedupe_key": key,
            "channel": channel,
            "trigger": CALLBACK_EVENTS[channel],
            "provider_call_id": payload.uuid,
            "provider_start_at": payload.start_stamp,
            "call_status": payload.call_status,
            "received_at": now,
            "expires_at": now + timedelta(days=30),
            "status": "test_observation" if test else "quarantined_observation",
        }
        try:
            await self.db.voice_provider_events.insert_one(doc)
            duplicate = False
        except DuplicateKeyError:
            existing = await self.db.voice_provider_events.find_one({"dedupe_key": key}, {"_id": 1})
            if existing is None:
                raise ConflictError(
                    "The event could not be reconciled with a durable record. Check storage indexes before retrying."
                ) from None
            duplicate = True
        return {"received": True, "duplicate": duplicate, "processing": "observation_only"}

    async def test_webhook(self, actor: User) -> dict[str, Any]:
        from app.features.voice_assistant.platform_service import require_component_testing

        await require_component_testing(self.db, "smartflo")
        doc = await self.document()
        if not doc.get("callback_token_encrypted"):
            raise ValidationError("Save a separate callback token before testing authentication.")
        # Check saved-secret decryptability and persistence, not provider delivery or reachability.
        try:
            token = decrypt(doc["callback_token_encrypted"])
        except InvalidToken as exc:
            raise ValidationError(
                "Stored callback credentials cannot be decrypted. Replace the callback token after checking the encryption key."
            ) from exc
        if len(token) < 32:
            raise ValidationError("Callback token is not sufficiently strong.")
        payload = SmartfloWebhookInput(uuid=f"test-{actor.require_id()}", start_stamp=utc_now())
        result = await self.ingest("incoming", payload, test=True)
        await self.audit(actor, "webhook_local_test")
        return {
            **result,
            "status": "local_persistence_passed",
            "message": "Local event persistence passed. Smartflo delivery, header authentication and public reachability remain unverified.",
        }

    async def events(self, page: int = 1) -> dict[str, Any]:
        query = {"provider": "smartflo", "expires_at": {"$gt": utc_now()}}
        rows = (
            await self.db.voice_provider_events.find(query, {"_id": 0, "dedupe_key": 0})
            .sort("received_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {"items": rows, "total": await self.db.voice_provider_events.count_documents(query)}
