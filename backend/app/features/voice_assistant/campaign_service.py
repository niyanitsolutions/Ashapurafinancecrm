import hashlib
import json
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from redis.asyncio import Redis

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.customer.service import CustomerService
from app.features.voice_assistant.campaign_schemas import (
    AudienceInput,
    CampaignAction,
    CampaignInput,
    ContactConsentInput,
    SuppressionInput,
)
from app.features.voice_assistant.repository import VoiceRepository, public
from app.features.voice_assistant.scheduling import next_window
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

CAMPAIGNS = "voice_campaigns"


async def ensure_campaign_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.voice_campaigns.create_index([("owner_user_id", 1), ("created_at", -1)])
    await db.voice_campaigns.create_index([("status", 1), ("scheduled_at", 1)])
    await db.voice_campaign_recipients.create_index(
        [("campaign_id", 1), ("customer_id", 1)], unique=True
    )
    await db.voice_campaign_recipients.create_index(
        [("campaign_id", 1), ("status", 1), ("lease_until", 1)]
    )
    await db.voice_campaign_imports.create_index(
        [("campaign_id", 1), ("idempotency_key", 1)], unique=True
    )
    await db.voice_contact_consents.create_index([("customer_id", 1), ("purpose", 1)], unique=True)
    await db.voice_contact_suppressions.create_index(
        [("customer_id", 1), ("scope", 1)], unique=True
    )


class CampaignService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self.db, self.redis = db, redis
        self.repo = VoiceRepository(db)
        self.engine = PermissionEngine(db)
        self.customers = CustomerService(db, redis)

    async def audit(self, actor_id: str, action: str, record_id: str) -> None:
        await write_audit_log(
            self.db,
            event_type=f"voice_assistant.campaign_{action}",
            user_id=actor_id,
            metadata={"record_id": record_id},
        )

    async def customer(self, customer_id: str, actor: User) -> None:
        if not await self.engine.has_permission(
            actor, module="customer", resource="customers", action="view"
        ):
            raise ForbiddenError("Customer View permission is required for campaign recipients.")
        customer = await self.customers.get_customer_for_staff(customer_id, actor)
        if customer.status != "active":
            raise ForbiddenError("Customer is not active.")

    async def get(self, record_id: str, actor: User) -> dict[str, Any]:
        doc = await self.repo.get(CAMPAIGNS, record_id)
        if record_id != str(doc["_id"]):
            raise ValidationError("Use the canonical lowercase campaign ID.")
        if actor.role != "owner" and doc["owner_user_id"] != actor.require_id():
            raise ForbiddenError("Campaign is outside your access scope.")
        return doc

    async def list(self, actor: User, page: int = 1) -> dict[str, Any]:
        query = {
            "is_deleted": False,
            **({} if actor.role == "owner" else {"owner_user_id": actor.require_id()}),
        }
        docs = (
            await self.db.voice_campaigns.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        items = []
        for doc in docs:
            counts = {
                state: await self.db.voice_campaign_recipients.count_documents(
                    {"campaign_id": str(doc["_id"]), "status": state}
                )
                for state in ("pending", "leased", "evaluated", "failed", "cancelled")
            }
            items.append({**public(doc), "processing_counts": counts})
        return {
            "items": items,
            "total": await self.db.voice_campaigns.count_documents(query),
            "page": page,
            "production_dispatch": "blocked",
            "compliance": "not_reviewed",
        }

    async def save(
        self, payload: CampaignInput, actor: User, record_id: str | None = None
    ) -> dict[str, Any]:
        if payload.mode != "dry_run":
            raise ForbiddenError(
                "Test/production dispatch is unavailable: transport, consent policy and staging approval are not verified."
            )
        fields = payload.model_dump(exclude={"version"})
        fields["scheduled_at"] = payload.scheduled_at or utc_now()
        if record_id:
            doc = await self.get(record_id, actor)
            if doc["version"] != payload.version or doc["status"] not in {
                "draft",
                "paused",
                "ready",
            }:
                raise ConflictError("Campaign changed or is not editable. Pause before editing.")
            if doc.get("import_lease_until") and doc["import_lease_until"] > utc_now():
                raise ConflictError("Audience import is processing. Retry shortly.")
            if await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id, "status": "leased", "lease_until": {"$gt": utc_now()}}
            ):
                raise ConflictError("Worker reservations must finish or expire before editing.")
            doc = await self.repo.update(
                CAMPAIGNS, doc, {**fields, "status": "draft"}, actor.require_id()
            )
            # New objectives/windows invalidate earlier dry-run decisions.
            await self.db.voice_campaign_recipients.update_many(
                {"campaign_id": record_id},
                {
                    "$set": {"status": "pending", "attempts": 0},
                    "$unset": {"decision": "", "lease_token": "", "lease_until": ""},
                },
            )
        else:
            now = utc_now()
            doc = {
                **fields,
                "status": "draft",
                "version": 1,
                "owner_user_id": actor.require_id(),
                "created_by": actor.require_id(),
                "created_at": now,
                "updated_at": now,
                "is_deleted": False,
            }
            doc["_id"] = (await self.db.voice_campaigns.insert_one(doc)).inserted_id
        await self.audit(actor.require_id(), "saved", str(doc["_id"]))
        return public(doc)

    async def action(self, record_id: str, payload: CampaignAction, actor: User) -> dict[str, Any]:
        doc = await self.get(record_id, actor)
        if doc["version"] != payload.version:
            raise ConflictError("Campaign changed. Refresh before this action.")
        if doc.get("import_lease_until") and doc["import_lease_until"] > utc_now():
            raise ConflictError("Audience import is processing.")
        transitions = {
            "validate": ({"draft", "paused"}, "ready"),
            "start": ({"ready"}, "running"),
            "pause": ({"ready", "running"}, "paused"),
            "resume": ({"paused"}, "running"),
            "cancel": ({"draft", "ready", "running", "paused"}, "cancelled"),
            "archive": ({"draft", "completed", "cancelled"}, "archived"),
        }
        origins, target = transitions[payload.action]
        if doc["status"] not in origins:
            raise ConflictError("Action is not valid for the current campaign state.")
        if target in {"ready", "running"}:
            if doc["mode"] != "dry_run":
                raise ForbiddenError("Live transport is not approved; no dispatch is allowed.")
            if await self.db.voice_campaign_controls.find_one(
                {"_id": "emergency", "stopped": True}
            ):
                raise ForbiddenError("Emergency stop is active. Owner review is required.")
            if not await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id}
            ):
                raise ValidationError("Add authorized recipients before starting a dry run.")
            if await self.db.voice_campaign_imports.count_documents(
                {"campaign_id": record_id, "status": "pending"}
            ):
                raise ConflictError("An audience import requires recovery before starting.")
        result = await self.repo.update(CAMPAIGNS, doc, {"status": target}, actor.require_id())
        if target == "cancelled":
            await self.db.voice_campaign_recipients.update_many(
                {"campaign_id": record_id, "status": {"$in": ["pending", "leased"]}},
                {"$set": {"status": "cancelled"}, "$unset": {"lease_token": "", "lease_until": ""}},
            )
        await self.audit(actor.require_id(), payload.action, record_id)
        return public(result)

    async def audience(self, record_id: str, payload: AudienceInput, actor: User) -> dict[str, Any]:
        doc = await self.get(record_id, actor)
        fingerprint = hashlib.sha256(
            json.dumps([r.model_dump() for r in payload.recipients], sort_keys=True).encode()
        ).hexdigest()
        receipt_key = {"campaign_id": record_id, "idempotency_key": payload.idempotency_key}
        receipt = await self.db.voice_campaign_imports.find_one(receipt_key)
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise ConflictError("Import key belongs to different recipient data.")
            if receipt["status"] == "completed":
                return public(receipt)
        if doc["status"] not in {"draft", "paused"} or (
            not receipt and doc["version"] != payload.version
        ):
            raise ConflictError(
                "Refresh the campaign and import recipients into a draft/paused campaign."
            )
        if doc.get("import_lease_until") and doc["import_lease_until"] > utc_now():
            raise ConflictError("Audience import is busy; retry with the same key.")
        # Validate every reference before writing any recipient; caller cannot supply contact data.
        for recipient in payload.recipients:
            await self.customer(recipient.customer_id, actor)
        doc = await self.repo.update(
            CAMPAIGNS,
            doc,
            {"import_lease_until": utc_now() + timedelta(seconds=120)},
            actor.require_id(),
        )
        if receipt is None:
            receipt = {
                **receipt_key,
                "fingerprint": fingerprint,
                "status": "pending",
                "created_at": utc_now(),
                "created_by": actor.require_id(),
                "input_count": len(payload.recipients),
            }
            try:
                receipt["_id"] = (
                    await self.db.voice_campaign_imports.insert_one(receipt)
                ).inserted_id
            except DuplicateKeyError:
                raise ConflictError("Concurrent import; retry with the same key.") from None
        try:
            existing = await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id}
            )
            incoming_ids = {r.customer_id for r in payload.recipients}
            duplicates = await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id, "customer_id": {"$in": list(incoming_ids)}}
            )
            if existing + len(incoming_ids) - duplicates > 10_000:
                raise ValidationError("Campaigns are limited to 10,000 unique recipients.")
            for recipient in payload.recipients:
                await self.check_import_lease(doc)
                await self.db.voice_campaign_recipients.update_one(
                    {"campaign_id": record_id, "customer_id": recipient.customer_id},
                    {
                        "$setOnInsert": {
                            "timezone": recipient.timezone or doc["timezone"],
                            "status": "pending",
                            "attempts": 0,
                            "created_at": utc_now(),
                        }
                    },
                    upsert=True,
                )
            total = await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id}
            )
            unique = len({r.customer_id for r in payload.recipients})
            await self.check_import_lease(doc)
            await self.db.voice_campaign_imports.update_one(
                {"_id": receipt["_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "unique_in_file": unique,
                        "duplicates_in_file": len(payload.recipients) - unique,
                        "total_recipients": total,
                        "completed_at": utc_now(),
                    }
                },
            )
            await self.audit(actor.require_id(), "audience_imported", record_id)
            return public(
                cast(
                    dict[str, Any],
                    await self.db.voice_campaign_imports.find_one({"_id": receipt["_id"]}),
                )
            )
        except ValidationError:
            await self.db.voice_campaign_imports.update_one(
                {"_id": receipt["_id"]}, {"$set": {"status": "rejected"}}
            )
            raise
        finally:
            await self.db.voice_campaigns.update_one(
                {"_id": doc["_id"], "version": doc["version"]},
                {"$unset": {"import_lease_until": ""}},
            )

    async def check_import_lease(self, doc: dict[str, Any]) -> None:
        current = await self.db.voice_campaigns.find_one(
            {
                "_id": doc["_id"],
                "version": doc["version"],
                "status": {"$in": ["draft", "paused"]},
                "import_lease_until": {"$gt": utc_now()},
            }
        )
        if current is None:
            raise ConflictError(
                "Audience import reservation expired or changed. Retry with the same key."
            )

    async def save_contact_policy(
        self, payload: ContactConsentInput | SuppressionInput, actor: User
    ) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only the Owner may attest contact policies.")
        await self.customer(payload.customer_id, actor)
        if isinstance(payload, ContactConsentInput):
            collection = "voice_contact_consents"
            key = {"customer_id": payload.customer_id, "purpose": payload.purpose}
            if payload.action == "grant" and payload.expires_at and payload.expires_at <= utc_now():
                raise ValidationError("Consent grant is already expired.")
            fields: dict[str, Any] = {
                "action": payload.action,
                "evidence_reference": payload.evidence_reference,
                "expires_at": payload.expires_at,
                "channel": "voice",
                "verification": "operator_attested_not_independently_verified",
            }
        else:
            collection = "voice_contact_suppressions"
            key = {"customer_id": payload.customer_id, "scope": payload.campaign_id or "global"}
            if payload.campaign_id:
                await self.get(payload.campaign_id, actor)
            fields = {"suppressed": payload.suppressed, "reason": payload.reason}
        current = await self.db[collection].find_one(key)
        history_entry = {
            **fields,
            "at": utc_now(),
            "actor_id": actor.require_id(),
            "version": payload.version + 1,
        }
        fields["history"] = [*(current or {}).get("history", [])[-99:], history_entry]
        if current:
            if current["version"] != payload.version:
                raise ConflictError("Contact policy changed. Refresh before updating.")
            result = await self.repo.update(collection, current, fields, actor.require_id())
        else:
            if payload.version != 1:
                raise ConflictError("New contact policy must start with version 1.")
            result = {
                **key,
                **fields,
                "version": 2,
                "is_deleted": False,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "created_by": actor.require_id(),
            }
            try:
                result["_id"] = (await self.db[collection].insert_one(result)).inserted_id
            except DuplicateKeyError:
                raise ConflictError(
                    "Contact policy was created concurrently. Refresh before retrying."
                ) from None
        await self.db.voice_contact_policy_events.insert_one(
            {
                "policy_id": str(result["_id"]),
                "kind": collection,
                "version": result["version"],
                "action": fields.get("action")
                or ("suppress" if fields.get("suppressed") else "unsuppress"),
                "created_at": utc_now(),
                "created_by": actor.require_id(),
            }
        )
        await self.audit(actor.require_id(), "contact_policy_updated", str(result["_id"]))
        return public(result)

    async def contact_policies(self, customer_id: str, actor: User) -> dict[str, Any]:
        await self.customer(customer_id, actor)
        return {
            "consents": [
                public(doc)
                async for doc in self.db.voice_contact_consents.find(
                    {"customer_id": customer_id}
                ).limit(100)
            ],
            "suppressions": [
                public(doc)
                async for doc in self.db.voice_contact_suppressions.find(
                    {"customer_id": customer_id}
                ).limit(100)
            ],
        }

    async def eligibility(
        self, campaign: dict[str, Any], recipient: dict[str, Any], actor: User
    ) -> dict[str, Any]:
        now = utc_now()
        customer_id = recipient["customer_id"]
        try:
            await self.customer(customer_id, actor)
        except (ForbiddenError, NotFoundError):
            return {"eligible": False, "reason": "customer_scope_or_status_denied"}
        if campaign["scheduled_at"] > now:
            return {
                "eligible": False,
                "reason": "campaign_not_due",
                "next_evaluation_at": campaign["scheduled_at"],
            }
        suppressions = await self.db.voice_contact_suppressions.find_one(
            {
                "customer_id": customer_id,
                "scope": {"$in": ["global", str(campaign["_id"])]},
                "suppressed": True,
            }
        )
        if suppressions:
            return {"eligible": False, "reason": "suppressed"}
        consent = await self.db.voice_contact_consents.find_one(
            {
                "customer_id": customer_id,
                "purpose": campaign["purpose"],
                "action": "grant",
                "expires_at": {"$gt": now},
            }
        )
        if consent is None:
            return {"eligible": False, "reason": "missing_or_expired_consent"}
        # Existing SMS/WhatsApp preferences are not permission for a voice call.
        last = await self.db.voice_campaign_recipients.find_one(
            {
                "customer_id": customer_id,
                "last_contact_at": {"$gt": now - timedelta(hours=campaign["frequency_hours"])},
            }
        )
        if last:
            return {"eligible": False, "reason": "contact_frequency_limit"}
        when = next_window(
            now,
            recipient["timezone"],
            campaign["calling_start"],
            campaign["calling_end"],
            campaign["holidays"],
            fold=campaign["dst_fold"],
        )
        return {
            "eligible": when == now,
            "reason": "dry_run_eligible" if when == now else "outside_calling_window",
            "next_window_at": when,
            "consent_version": consent["version"],
            "production_dispatch": "blocked_unverified_transport_and_policy",
        }

    async def recipients(self, record_id: str, actor: User, page: int = 1) -> dict[str, Any]:
        await self.get(record_id, actor)
        docs = (
            await self.db.voice_campaign_recipients.find({"campaign_id": record_id})
            .sort("created_at", 1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        items = []
        for doc in docs:
            try:
                await self.customer(doc["customer_id"], actor)
            except (ForbiddenError, NotFoundError):
                continue
            items.append(
                public(
                    {
                        key: value
                        for key, value in doc.items()
                        if key not in {"lease_token", "lease_until"}
                    }
                )
            )
        return {
            "items": items,
            "total": await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": record_id}
            ),
            "page": page,
        }

    async def preview(self, record_id: str, actor: User, page: int = 1) -> dict[str, Any]:
        campaign = await self.get(record_id, actor)
        rows = (
            await self.db.voice_campaign_recipients.find({"campaign_id": record_id})
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        decisions = []
        for row in rows:
            decision = await self.eligibility(campaign, row, actor)
            if decision["reason"] != "customer_scope_or_status_denied":
                decisions.append({"customer_id": row["customer_id"], **decision})
        await self.audit(actor.require_id(), "previewed", record_id)
        return {
            "items": decisions,
            "page": page,
            "mode": "dry_run",
            "calls_placed": 0,
            "production_dispatch": "blocked",
            "compliance": "not_reviewed",
        }

    async def emergency(self, stopped: bool, reason: str, actor: User) -> dict[str, Any]:
        if actor.role != "owner":
            raise ForbiddenError("Only the Owner may change the emergency stop.")
        await self.db.voice_campaign_controls.update_one(
            {"_id": "emergency"},
            {
                "$set": {
                    "stopped": stopped,
                    "reason": reason,
                    "updated_at": utc_now(),
                    "updated_by": actor.require_id(),
                }
            },
            upsert=True,
        )
        if stopped:
            await self.db.voice_campaigns.update_many(
                {"status": {"$in": ["running", "ready"]}},
                {"$set": {"status": "paused"}, "$inc": {"version": 1}},
            )
        await self.audit(actor.require_id(), "emergency_changed", "emergency")
        return {
            "stopped": stopped,
            "production_dispatch": "blocked",
            "live_calls_terminated": False,
        }

    async def sweep(self) -> dict[str, int]:
        processed = failed = 0
        if await self.db.voice_campaign_controls.find_one({"_id": "emergency", "stopped": True}):
            return {"processed": 0, "failed": 0}
        async for campaign in self.db.voice_campaigns.find(
            {
                "status": "running",
                "mode": "dry_run",
                "scheduled_at": {"$lte": utc_now()},
                "is_deleted": False,
            }
        ).limit(4):
            campaign_id = str(campaign["_id"])
            actor = await UserRepository(self.db).find_by_id(campaign["owner_user_id"])
            if (
                not actor
                or actor.status != ACCOUNT_STATUS_ACTIVE
                or not await self.engine.has_permission(
                    actor, module="voice_assistant", resource="campaigns", action="edit"
                )
            ):
                await self.db.voice_campaigns.update_one(
                    {"_id": campaign["_id"], "version": campaign["version"]},
                    {
                        "$set": {"status": "paused", "blocked_reason": "principal_revoked"},
                        "$inc": {"version": 1},
                    },
                )
                continue
            for _ in range(50):
                now, token = utc_now(), uuid4().hex
                row = await self.db.voice_campaign_recipients.find_one_and_update(
                    {
                        "campaign_id": campaign_id,
                        "$or": [
                            {"status": "pending"},
                            {"status": "leased", "lease_until": {"$lte": now}},
                        ],
                    },
                    {
                        "$set": {
                            "status": "leased",
                            "lease_token": token,
                            "lease_until": now + timedelta(seconds=30),
                        },
                        "$inc": {"attempts": 1},
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if row is None:
                    break
                try:
                    actor = await UserRepository(self.db).find_by_id(campaign["owner_user_id"])
                    if (
                        not actor
                        or actor.status != ACCOUNT_STATUS_ACTIVE
                        or not await self.engine.has_permission(
                            actor, module="voice_assistant", resource="campaigns", action="edit"
                        )
                    ):
                        raise ForbiddenError("Campaign principal was revoked.")
                    current = await self.get(campaign_id, actor)
                    stopped = await self.db.voice_campaign_controls.find_one(
                        {"_id": "emergency", "stopped": True}
                    )
                    if current["status"] != "running" or stopped:
                        decision = {"eligible": False, "reason": "campaign_stopped"}
                    else:
                        decision = await self.eligibility(current, row, actor)
                        latest = await self.db.voice_campaigns.find_one({"_id": campaign["_id"]})
                        if (
                            not latest
                            or latest["status"] != "running"
                            or latest["version"] != current["version"]
                        ):
                            decision = {"eligible": False, "reason": "campaign_stopped"}
                    outcome = "evaluated"
                except (ValidationError, ForbiddenError, NotFoundError):
                    decision, outcome = (
                        {"eligible": False, "reason": "eligibility_failed"},
                        "failed",
                    )
                if row["attempts"] > campaign["maximum_attempts"]:
                    decision, outcome = (
                        {"eligible": False, "reason": "reservation_retry_exhausted"},
                        "failed",
                    )
                result = await self.db.voice_campaign_recipients.update_one(
                    {
                        "_id": row["_id"],
                        "status": "leased",
                        "lease_token": token,
                        "lease_until": {"$gt": utc_now()},
                    },
                    {
                        "$set": {
                            "status": outcome,
                            "decision": decision,
                            "evaluated_at": utc_now(),
                        },
                        "$unset": {"lease_token": "", "lease_until": ""},
                    },
                )
                processed += int(result.modified_count)
                failed += int(bool(result.modified_count) and outcome == "failed")
            if not await self.db.voice_campaign_recipients.count_documents(
                {"campaign_id": campaign_id, "status": {"$in": ["pending", "leased"]}}
            ):
                await self.db.voice_campaigns.update_one(
                    {"_id": campaign["_id"], "status": "running", "version": campaign["version"]},
                    {"$set": {"status": "completed"}, "$inc": {"version": 1}},
                )
        await self.db.voice_worker_health.update_one(
            {"singleton_key": "campaigns"},
            {"$set": {"heartbeat_at": utc_now(), "processed": processed, "failed": failed}},
            upsert=True,
        )
        return {"processed": processed, "failed": failed}
