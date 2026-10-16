import json
from datetime import timedelta
from typing import Any

from cryptography.fernet import InvalidToken
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.native_adapter import AsteriskReadOnlyAdapter
from app.features.voice_assistant.native_config import NativeConnectionInput, get_native_config
from app.features.voice_assistant.number_schemas import TelephoneNumberAction, TelephoneNumberInput
from app.features.voice_assistant.platform_service import require_component_testing
from app.features.voice_assistant.repository import VoiceRepository, public
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

CONNECTIONS = "voice_native_connections"
NUMBERS = "voice_phone_numbers"


async def ensure_native_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db[CONNECTIONS].create_index("name", unique=True)
    await db[NUMBERS].create_index("number", unique=True)
    await db[NUMBERS].create_index([("connection_id", 1), ("state", 1)])
    await db.voice_native_tests.create_index([("connection_id", 1), ("created_at", -1)])


def safe_connection(doc: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: doc.get(key)
        for key in (
            "_id",
            "name",
            "adapter",
            "api_origin",
            "endpoint_name",
            "state",
            "version",
            "created_at",
            "updated_at",
            "last_test",
        )
    }
    return {
        **public(result),
        "credentials_configured": bool(doc.get("credentials_encrypted")),
        "live_calling": False,
        "media_verified": False,
    }


class NativeVoiceService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db, self.repo = db, VoiceRepository(db)

    async def audit(self, actor: User, action: str, record_id: str) -> None:
        await write_audit_log(
            self.db,
            event_type=f"voice_assistant.native_{action}",
            user_id=actor.require_id(),
            metadata={"record_id": record_id},
        )

    async def record(self, collection: str, record_id: str) -> dict[str, Any]:
        doc = await self.repo.get(collection, record_id)
        if str(doc["_id"]) != record_id:
            raise ValidationError("Use the canonical lowercase record ID.")
        return doc

    async def connections(self, actor: User, page: int = 1) -> dict[str, Any]:
        owner_only(actor)
        query = {"is_deleted": False}
        docs = (
            await self.db[CONNECTIONS]
            .find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {
            "items": [safe_connection(doc) for doc in docs],
            "total": await self.db[CONNECTIONS].count_documents(query),
            "page": page,
            "live_calling": False,
            "adapter_scope": "read_only_ari_probe",
            "origin_allowlist_configured": bool(get_native_config().allowed_origins),
        }

    async def save_connection(
        self, payload: NativeConnectionInput, actor: User, record_id: str | None = None
    ) -> dict[str, Any]:
        owner_only(actor)
        old = await self.record(CONNECTIONS, record_id) if record_id else None
        if old and old["version"] != payload.version:
            raise ConflictError("Connection changed. Refresh before saving.")
        fields: dict[str, Any] = {
            "name": payload.name,
            "adapter": "asterisk_ari",
            "api_origin": payload.api_origin,
            "endpoint_name": payload.endpoint_name,
            "last_test": None,
            "state": "verification_pending",
        }
        if payload.password and payload.username:
            fields["credentials_encrypted"] = encrypt(
                json.dumps(
                    {
                        "username": payload.username.get_secret_value(),
                        "password": payload.password.get_secret_value(),
                    }
                )
            )
        elif payload.clear_credentials:
            fields["credentials_encrypted"] = None
        credentials = fields.get("credentials_encrypted", (old or {}).get("credentials_encrypted"))
        if not credentials or payload.api_origin not in get_native_config().allowed_origins:
            fields["state"] = "configuration_incomplete"
        try:
            if old:
                doc = await self.repo.update(CONNECTIONS, old, fields, actor.require_id())
            else:
                now = utc_now()
                doc = {
                    **fields,
                    "version": 1,
                    "is_deleted": False,
                    "created_at": now,
                    "updated_at": now,
                    "created_by": actor.require_id(),
                }
                doc["_id"] = (await self.db[CONNECTIONS].insert_one(doc)).inserted_id
        except DuplicateKeyError:
            raise ConflictError("Connection name already exists.") from None
        # Credential/routing changes cannot preserve activation or previous evidence.
        if old:
            await self.db[NUMBERS].update_many(
                {
                    "connection_id": record_id,
                    "state": {"$nin": ["disabled", "revoked", "rejected", "suspended"]},
                },
                {
                    "$set": {"state": "verification_pending", "updated_at": utc_now()},
                    "$inc": {"version": 1},
                },
            )
        await self.audit(actor, "connection_saved", str(doc["_id"]))
        return safe_connection(doc)

    async def test_connection(self, record_id: str, actor: User) -> dict[str, Any]:
        owner_only(actor)
        await require_component_testing(self.db, "telephony")
        doc = await self.record(CONNECTIONS, record_id)
        if doc["api_origin"] not in get_native_config().allowed_origins:
            raise ForbiddenError(
                "PBX origin is not in the server-managed VOICE_NATIVE_ALLOWED_ORIGINS allowlist. No request was sent."
            )
        if not doc.get("credentials_encrypted"):
            raise ValidationError("Configure server-side PBX credentials before testing.")
        try:
            credentials = json.loads(decrypt(doc["credentials_encrypted"]))
            probe = AsteriskReadOnlyAdapter(
                doc["api_origin"], credentials["username"], credentials["password"]
            )
        except (ValueError, KeyError, TypeError, InvalidToken):
            raise ValidationError(
                "Stored PBX credentials are unavailable; rotate them before testing."
            ) from None
        result = await probe.probe(doc["endpoint_name"])
        now = utc_now()
        evidence = {
            **result,
            "checked_at": now,
            "configuration_version": doc["version"],
            "scope": "read_only_api_and_endpoint_probe",
            "calls_placed": 0,
        }
        await self.db.voice_native_tests.insert_one(
            {
                "connection_id": record_id,
                "created_at": now,
                "created_by": actor.require_id(),
                **evidence,
            }
        )
        updated = await self.repo.update(
            CONNECTIONS,
            doc,
            {
                "last_test": evidence,
                "state": "control_probe_passed"
                if result["status"] == "control_probe_passed"
                else "verification_failed",
            },
            actor.require_id(),
        )
        await self.audit(actor, "connection_tested", record_id)
        return safe_connection(updated)

    async def connection_events(self, record_id: str, actor: User, page: int = 1) -> dict[str, Any]:
        owner_only(actor)
        await self.record(CONNECTIONS, record_id)
        query = {"connection_id": record_id}
        docs = (
            await self.db.voice_native_tests.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {
            "items": [public(doc) for doc in docs],
            "total": await self.db.voice_native_tests.count_documents(query),
            "page": page,
        }

    async def save_number(
        self, payload: TelephoneNumberInput, actor: User, record_id: str | None = None
    ) -> dict[str, Any]:
        owner_only(actor)
        old = await self.record(NUMBERS, record_id) if record_id else None
        if old and old["state"] == "revoked":
            raise ForbiddenError(
                "Revoked number authorization cannot be restored by editing a draft."
            )
        if old and (old["version"] != payload.version or old["state"] == "active"):
            raise ConflictError(
                "Number changed or is active. Refresh and suspend it before editing."
            )
        if old and old["number"] != payload.number:
            raise ValidationError(
                "A registered telephone number is immutable; register a new number instead."
            )
        if payload.connection_id:
            await self.record(CONNECTIONS, payload.connection_id)
        fields: dict[str, Any] = payload.model_dump(exclude={"version"})
        fields.update(
            {
                "state": "draft",
                "approval_evidence": "owner_reference_not_provider_verified",
                "live_calling": False,
            }
        )
        try:
            if old:
                doc = await self.repo.update(NUMBERS, old, fields, actor.require_id())
            else:
                now = utc_now()
                doc = {
                    **fields,
                    "version": 1,
                    "is_deleted": False,
                    "created_at": now,
                    "updated_at": now,
                    "created_by": actor.require_id(),
                }
                doc["_id"] = (await self.db[NUMBERS].insert_one(doc)).inserted_id
        except DuplicateKeyError:
            raise ConflictError(
                "Telephone number is already registered; update its existing record."
            ) from None
        await self.audit(actor, "number_saved", str(doc["_id"]))
        return await self.number_status(doc)

    async def number_status(self, doc: dict[str, Any]) -> dict[str, Any]:
        connection = None
        if doc.get("connection_id"):
            connection = await self.record(CONNECTIONS, doc["connection_id"])
        evidence = (connection or {}).get("last_test") or {}
        fresh = bool(
            connection
            and evidence.get("checked_at")
            and evidence["checked_at"] > utc_now() - timedelta(minutes=15)
            and evidence.get("configuration_version") == connection["version"] - 1
        )
        checks = [
            {
                "key": "authorization_reference",
                "passed": bool(doc.get("authorization_reference")),
                "description": "Owner authorization reference supplied; independent telecom approval remains separate.",
            },
            {
                "key": "connection_configured",
                "passed": bool(connection and connection.get("credentials_encrypted")),
                "description": "Native PBX connection and server-side credentials configured.",
            },
            {
                "key": "control_probe",
                "passed": fresh and evidence.get("status") == "control_probe_passed",
                "description": "Read-only ARI and endpoint probe passed within 15 minutes for the current configuration.",
            },
            {
                "key": "telecom_approval",
                "passed": False,
                "description": "Provider provisioning, number ownership, approved caller identity and directional capabilities require verified evidence.",
            },
            {
                "key": "media",
                "passed": False,
                "description": "Authenticated two-way media and interruption handling are not staging verified.",
            },
            {
                "key": "self_hosted_ai",
                "passed": False,
                "description": "Approved self-hosted STT, TTS and LLM representative request checks are not verified.",
            },
            {
                "key": "consent_compliance",
                "passed": False,
                "description": "Recording, consent, suppression, hours and compliance acceptance are not approved.",
            },
            {
                "key": "acceptance",
                "passed": False,
                "description": "Call control, reconciliation, outage fallback and staging acceptance are outstanding.",
            },
        ]
        return {
            **public(doc),
            "activation_checks": checks,
            "activation_eligible": all(check["passed"] for check in checks),
            "live_calling": False,
            "control_evidence_fresh": fresh,
        }

    async def numbers(self, actor: User, page: int = 1) -> dict[str, Any]:
        owner_only(actor)
        query = {"is_deleted": False}
        docs = (
            await self.db[NUMBERS]
            .find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {
            "items": [await self.number_status(doc) for doc in docs],
            "total": await self.db[NUMBERS].count_documents(query),
            "page": page,
            "live_calling": False,
        }

    async def number_action(
        self, record_id: str, payload: TelephoneNumberAction, actor: User
    ) -> dict[str, Any]:
        owner_only(actor)
        doc = await self.record(NUMBERS, record_id)
        if doc["version"] != payload.version:
            raise ConflictError("Number changed. Refresh before applying an action.")
        if payload.action == "activate":
            status = await self.number_status(doc)
            blockers = [
                check["description"] for check in status["activation_checks"] if not check["passed"]
            ]
            await self.audit(actor, "number_activation_denied", record_id)
            raise ForbiddenError(
                "Live activation is blocked until the native control/media runtime and required approvals are verified.",
                details={"blockers": blockers},
            )
        if doc["state"] == "revoked" and payload.action != "revoke":
            raise ForbiddenError(
                "Revoked authorization is terminal; obtain a separately reviewed authorization workflow."
            )
        target = {
            "disable": "disabled",
            "suspend": "suspended",
            "reject": "rejected",
            "revoke": "revoked",
        }.get(payload.action)
        if target is None:
            status = await self.number_status(doc)
            target = (
                "awaiting_telecom_approval"
                if not doc.get("authorization_reference")
                else "configuration_incomplete"
                if not doc.get("connection_id")
                else "verification_pending"
            )
            if status["control_evidence_fresh"]:
                target = "awaiting_acceptance"
        event = {
            "action": payload.action,
            "reason": payload.reason,
            "at": utc_now(),
            "actor_id": actor.require_id(),
        }
        updated = await self.repo.update(
            NUMBERS,
            doc,
            {"state": target, "timeline": [*doc.get("timeline", [])[-99:], event]},
            actor.require_id(),
        )
        await self.audit(actor, f"number_{payload.action}", record_id)
        return await self.number_status(updated)
