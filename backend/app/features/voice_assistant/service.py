import hashlib
import re
from datetime import UTC, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.features.auth.models import User
from app.features.voice_assistant.adapters import readiness
from app.features.voice_assistant.conversation import (
    LocalConversationAdapter,
    get_conversation_config,
)
from app.features.voice_assistant.models import (
    TERMINAL,
    TRANSITIONS,
    CallSession,
    KnowledgeArticle,
)
from app.features.voice_assistant.repository import VoiceRepository, public
from app.features.voice_assistant.schemas import (
    CallAction,
    ConsoleInput,
    KnowledgeAction,
    KnowledgeInput,
    MockCallInput,
    VoiceSettings,
)
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now

CALLS = "voice_calls"
KNOWLEDGE = "voice_knowledge"


class VoiceService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = VoiceRepository(db)

    async def audit(self, actor: User, action: str, record_id: str | None = None) -> None:
        await write_audit_log(
            self.db,
            event_type=f"voice_assistant.{action}",
            user_id=actor.require_id(),
            metadata={"record_id": record_id},
        )

    async def settings(self) -> VoiceSettings:
        doc = await self.db.voice_settings.find_one({"singleton_key": "default"})
        fields = VoiceSettings.model_fields
        return VoiceSettings.model_validate({k: v for k, v in (doc or {}).items() if k in fields})

    async def save_settings(self, payload: VoiceSettings, actor: User) -> VoiceSettings:
        if payload.primary_employee_id:
            if not ObjectId.is_valid(payload.primary_employee_id):
                raise ValidationError("Select a valid employee.")
            employee = await self.db.employees.find_one(
                {
                    "_id": ObjectId(payload.primary_employee_id),
                    "is_deleted": False,
                    "status": "active",
                }
            )
            if not employee:
                raise ValidationError("Select an active employee.")
        data = payload.model_dump(mode="json")
        data["version"] += 1
        try:
            result = await self.db.voice_settings.find_one_and_update(
                {"singleton_key": "default", "version": payload.version},
                {
                    "$set": {**data, "updated_by": actor.require_id(), "updated_at": utc_now()},
                    "$push": {
                        "revisions": {
                            "$each": [
                                {
                                    **data,
                                    "saved_by": actor.require_id(),
                                    "saved_at": utc_now(),
                                }
                            ],
                            "$slice": -20,
                        }
                    },
                },
                upsert=payload.version == 1,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ConflictError("Settings changed. Refresh and retry.") from exc
        if result is None:
            raise ConflictError("Settings changed. Refresh and retry.")
        await self.audit(actor, "settings_updated")
        return VoiceSettings.model_validate(
            {k: v for k, v in result.items() if k in VoiceSettings.model_fields}
        )

    def scope(self, actor: User) -> dict[str, Any]:
        # Calls are private to their creator. Broad view grants never imply all-customer access.
        return {
            "is_deleted": False,
            **({} if actor.role == "owner" else {"owner_user_id": actor.require_id()}),
        }

    async def call(self, record_id: str, actor: User) -> dict[str, Any]:
        doc = await self.repo.get(CALLS, record_id)
        if actor.role != "owner" and doc["owner_user_id"] != actor.require_id():
            raise ForbiddenError("This call is outside your access scope.")
        return doc

    async def list_calls(
        self,
        actor: User,
        *,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        query = self.scope(actor)
        if status:
            query["status"] = {"$nin": list(TERMINAL)} if status == "active" else status
        if direction:
            query["direction"] = direction
        total = await self.db.voice_calls.count_documents(query)
        docs = (
            await self.db.voice_calls.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list(page_size)
        )
        return {
            "items": [public(d) for d in docs],
            "total": total,
            "page": page,
            "total_pages": (total + page_size - 1) // page_size,
        }

    async def dashboard(self, actor: User) -> dict[str, Any]:
        cfg = await self.settings()
        now = utc_now()
        local = now.astimezone(ZoneInfo(cfg.timezone))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        query = {**self.scope(actor), "created_at": {"$gte": start}}
        metrics: dict[str, int | float] = {
            "incoming": 0,
            "outgoing": 0,
            "answered": 0,
            "missed": 0,
            "failed": 0,
            "ai_handled": 0,
            "human_handled": 0,
            "successful_transfers": 0,
            "total_seconds": 0,
        }
        count = 0
        async for doc in self.db.voice_calls.find(query):
            count += 1
            metrics[doc["direction"]] += 1
            metrics["answered"] += bool(doc.get("answered_at"))
            for state in ("missed", "failed"):
                metrics[state] += doc["status"] == state
            states = {event["state"] for event in doc.get("timeline", [])}
            metrics["ai_handled"] += "ai_active" in states
            metrics["human_handled"] += "human_active" in states
            metrics["successful_transfers"] += doc.get("transfer_outcome") == "confirmed"
            metrics["total_seconds"] += doc.get("duration_seconds", 0)
        metrics["average_seconds"] = round(metrics["total_seconds"] / count, 1) if count else 0
        metrics["active"] = await self.db.voice_calls.count_documents(
            {**self.scope(actor), "status": {"$nin": list(TERMINAL)}}
        )
        health = await self.db.voice_worker_health.find_one({"singleton_key": "default"})
        heartbeat = health.get("heartbeat_at") if health else None
        worker = (
            "healthy"
            if heartbeat and now - heartbeat < timedelta(seconds=90)
            else "unknown_or_stale"
        )
        return {
            "metrics": metrics,
            "data_mode": "mock_only",
            "estimated_cost": None,
            "provider": readiness(),
            "worker": worker,
            "worker_heartbeat_at": heartbeat,
            "recent": (await self.list_calls(actor, page_size=8))["items"],
        }

    async def create_mock_call(self, payload: MockCallInput, actor: User) -> dict[str, Any]:
        cfg = await self.settings()
        if cfg.mode != "mock":
            raise ForbiddenError("Enable mock mode in Settings before simulating calls.")
        existing = await self.db.voice_calls.find_one({"idempotency_key": payload.idempotency_key})
        if existing:
            await self.call(str(existing["_id"]), actor)
            if (
                existing["direction"] != payload.direction
                or existing["contact_label"] != payload.contact_label
                or existing.get("consent_reference") != payload.consent_reference
            ):
                raise ConflictError("Idempotency key belongs to a different request.")
            return public(existing)
        now = utc_now()
        local = now.astimezone(ZoneInfo(cfg.timezone))
        if payload.direction == "outgoing":
            if not payload.consent_reference:
                raise ForbiddenError(
                    "A consent evidence reference is required, including in simulations."
                )
            if (
                local.date() in cfg.holidays
                or not cfg.calling_start <= local.strftime("%H:%M") < cfg.calling_end
            ):
                raise ForbiddenError("Outside the configured calling window.")
        # Serializes simulator admission across API processes. No live dialing is implemented here.
        token = uuid4().hex
        try:
            lease = await self.db.voice_admission.find_one_and_update(
                {
                    "_id": "default",
                    "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}],
                },
                {"$set": {"token": token, "expires_at": now + timedelta(seconds=30)}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ConflictError("Call admission is busy. Retry shortly with the same key.") from exc
        if not lease:
            raise ConflictError("Call admission is busy. Retry shortly.")
        try:
            active = await self.db.voice_calls.count_documents({"status": {"$nin": list(TERMINAL)}})
            if active >= cfg.max_concurrent_calls:
                raise ConflictError("Maximum concurrent simulated calls reached.")
            day = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
            if (
                await self.db.voice_calls.count_documents({"created_at": {"$gte": day}})
                >= cfg.daily_call_limit
            ):
                raise ConflictError("Daily call limit reached.")
            if (
                await self.db.voice_calls.count_documents(
                    {
                        "created_at": {"$gte": now - timedelta(minutes=1)},
                    }
                )
                >= cfg.calls_per_minute
            ):
                raise ConflictError("Calls per minute limit reached.")
            month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
            used = 0
            async for row in self.db.voice_calls.find({"created_at": {"$gte": month}}):
                used += (
                    row.get("duration_seconds", 0)
                    if row["status"] in TERMINAL
                    else cfg.max_duration_seconds
                )
            if used + cfg.max_duration_seconds > cfg.monthly_minute_limit * 60:
                raise ConflictError(
                    "Monthly minutes limit reached, including reserved active-call minutes."
                )
            doc = CallSession(
                direction=payload.direction,
                contact_label=payload.contact_label,
                idempotency_key=payload.idempotency_key,
                owner_user_id=actor.require_id(),
                created_by=actor.require_id(),
                assigned_employee_id=cfg.primary_employee_id,
                language=cfg.default_language,
                deadline_at=now + timedelta(seconds=cfg.ring_seconds),
                consent_reference=payload.consent_reference,
                timeline=[{"state": "ringing", "at": now, "reason": "mock_created"}],
            ).model_dump(by_alias=True, exclude={"id"})
            # A lease expiration never grants permission to continue a stale admission attempt.
            if utc_now() >= lease["expires_at"]:
                raise ConflictError("Admission timed out. Retry with the same key.")
            try:
                result = await self.db.voice_calls.insert_one(doc)
                doc["_id"] = result.inserted_id
            except DuplicateKeyError:
                duplicate = await self.db.voice_calls.find_one(
                    {"idempotency_key": payload.idempotency_key}
                )
                if duplicate is None:
                    raise ConflictError(
                        "Duplicate admission could not be reconciled. Retry shortly."
                    )
                await self.call(str(duplicate["_id"]), actor)
                return public(duplicate)
            await self.audit(actor, "mock_created", str(doc["_id"]))
            return public(doc)
        finally:
            await self.db.voice_admission.delete_one({"_id": "default", "token": token})

    async def transition(
        self,
        doc: dict[str, Any],
        target: str,
        *,
        actor_id: str,
        reason: str,
        updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if target not in TRANSITIONS.get(doc["status"], set()):
            raise ConflictError(f"Cannot transition {doc['status']} to {target}.")
        now = utc_now()
        cfg = await self.settings()
        changes = {**(updates or {}), "status": target}
        if target in {"human_active", "ai_active"} and not doc.get("answered_at"):
            changes["answered_at"] = now
        if target in {"human_active", "ai_active", "transferring"}:
            answered = doc.get("answered_at") or changes.get("answered_at") or now
            max_end = answered + timedelta(seconds=cfg.max_duration_seconds)
            changes["deadline_at"] = (
                min(max_end, now + timedelta(seconds=cfg.transfer_seconds))
                if target == "transferring"
                else max_end
            )
        if target in TERMINAL:
            changes["ended_at"] = now
            changes["duration_seconds"] = (
                max(0, int((now - doc["answered_at"]).total_seconds()))
                if doc.get("answered_at")
                else 0
            )
        return await self.repo.update(
            CALLS,
            doc,
            changes,
            actor_id,
            {"state": target, "at": now, "reason": reason},
        )

    async def act(self, record_id: str, payload: CallAction, actor: User) -> dict[str, Any]:
        doc = await self.call(record_id, actor)
        if doc["version"] != payload.version:
            raise ConflictError("Call changed. Refresh before retrying.")
        if doc["status"] in TERMINAL:
            raise ConflictError("Call has ended.")
        if doc["deadline_at"] <= utc_now():
            raise ConflictError("Call deadline has passed. Wait for worker reconciliation.")
        cfg = await self.settings()
        targets = {
            "answer": "human_active",
            "reject": "ai_active" if cfg.ai_fallback else "missed",
            "transfer": "transferring",
            "transfer_confirmed": "human_active",
            "transfer_failed": "ai_active" if cfg.ai_fallback else "completed",
            "end": "completed",
        }
        if cfg.mode != "mock" and payload.action != "end":
            raise ForbiddenError(
                "Mock mode is disabled. Only ending an existing session is allowed."
            )
        required = {
            "answer": "ringing",
            "reject": "ringing",
            "transfer": "ai_active",
            "transfer_confirmed": "transferring",
            "transfer_failed": "transferring",
        }
        if payload.action in required and doc["status"] != required[payload.action]:
            raise ConflictError("This action is not valid for the current call state.")
        updates = {}
        if payload.action.startswith("transfer"):
            updates["transfer_outcome"] = {
                "transfer": "pending",
                "transfer_confirmed": "confirmed",
                "transfer_failed": "failed",
            }[payload.action]
        result = await self.transition(
            doc,
            targets[payload.action],
            actor_id=actor.require_id(),
            reason=f"mock_{payload.action}",
            updates=updates,
        )
        await self.audit(actor, f"mock_{payload.action}", record_id)
        return public(result)

    async def sweep(self) -> int:
        now = utc_now()
        cfg = await self.settings()
        processed = 0
        due: dict[str, Any] = {"status": {"$nin": list(TERMINAL)}}
        if cfg.mode == "mock":
            due["deadline_at"] = {"$lte": now}
        async for doc in self.db.voice_calls.find(due).limit(200):
            state = doc["status"]
            target = "completed"
            updates = {}
            if state == "ringing":
                target = "ai_active" if cfg.ai_fallback and cfg.mode == "mock" else "missed"
            elif state == "transferring":
                target = "ai_active" if cfg.ai_fallback else "completed"
                updates["transfer_outcome"] = "timed_out"
            elif state == "queued":
                target = "cancelled"
            if cfg.mode == "disabled" and state not in {"ringing", "queued"}:
                target = "completed"
            if doc.get("answered_at") and now >= doc["answered_at"] + timedelta(
                seconds=cfg.max_duration_seconds
            ):
                target = "completed"
            try:
                await self.transition(
                    doc, target, actor_id="voice-worker", reason="mock_deadline", updates=updates
                )
                processed += 1
            except ConflictError:
                continue
        await self.db.voice_worker_health.update_one(
            {"singleton_key": "default"},
            {"$set": {"heartbeat_at": now}},
            upsert=True,
        )
        return processed

    async def list_knowledge(self, page: int = 1) -> dict[str, Any]:
        docs = (
            await self.db.voice_knowledge.find({"is_deleted": False})
            .sort("updated_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        return {
            "items": [public(d) for d in docs],
            "total": await self.db.voice_knowledge.count_documents({"is_deleted": False}),
        }

    def knowledge_fields(self, payload: KnowledgeInput) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", payload.content).strip()
        return {
            "title": payload.title,
            "content": payload.content,
            "language": payload.language,
            "content_hash": hashlib.sha256(normalized.encode()).hexdigest(),
            "chunks": [normalized[i : i + 1000] for i in range(0, len(normalized), 850)],
            "effective_on": payload.effective_on.isoformat() if payload.effective_on else None,
            "expires_on": payload.expires_on.isoformat() if payload.expires_on else None,
        }

    async def save_knowledge(
        self, payload: KnowledgeInput, actor: User, record_id: str | None = None
    ) -> dict[str, Any]:
        fields = self.knowledge_fields(payload)
        duplicate = await self.db.voice_knowledge.find_one(
            {"content_hash": fields["content_hash"], "is_deleted": False}
        )
        if duplicate and str(duplicate["_id"]) != record_id:
            raise ConflictError("This content already exists in the knowledge library.")
        if record_id:
            doc = await self.repo.get(KNOWLEDGE, record_id)
            if doc["version"] != payload.version:
                raise ConflictError("Knowledge changed. Refresh before retrying.")
            revisions = [
                *doc["revisions"],
                {
                    k: doc[k]
                    for k in (
                        "title",
                        "content",
                        "language",
                        "effective_on",
                        "expires_on",
                        "version",
                    )
                },
            ]
            result = await self.repo.update(
                KNOWLEDGE,
                doc,
                {**fields, "status": "draft", "reviewed_by": None, "revisions": revisions[-20:]},
                actor.require_id(),
            )
        else:
            result = KnowledgeArticle(**fields, created_by=actor.require_id()).model_dump(
                by_alias=True,
                exclude={"id"},
            )
            try:
                inserted = await self.db.voice_knowledge.insert_one(result)
            except DuplicateKeyError as exc:
                raise ConflictError(
                    "This content already exists in the knowledge library."
                ) from exc
            result["_id"] = inserted.inserted_id
        await self.audit(actor, "knowledge_saved", str(result["_id"]))
        return public(result)

    async def knowledge_action(
        self, record_id: str, payload: KnowledgeAction, actor: User
    ) -> dict[str, Any]:
        doc = await self.repo.get(KNOWLEDGE, record_id)
        if payload.version != doc["version"]:
            raise ConflictError("Knowledge changed. Refresh before retrying.")
        transitions = {"review": ("draft", "review"), "publish": ("review", "published")}
        updates = {}
        if payload.action in transitions:
            origin, target = transitions[payload.action]
            if doc["status"] != origin:
                raise ConflictError(f"Knowledge must be {origin} first.")
            updates["status"] = target
            if target == "published":
                updates["reviewed_by"] = actor.require_id()
        elif payload.action == "archive":
            updates["status"] = "archived"
        else:
            revision = next(
                (r for r in doc["revisions"] if r["version"] == payload.target_version), None
            )
            if not revision:
                raise ValidationError("That retained revision does not exist.")
            from app.features.voice_assistant.schemas import KnowledgeInput

            return await self.save_knowledge(
                KnowledgeInput(**{**revision, "version": doc["version"]}), actor, record_id
            )
        result = await self.repo.update(KNOWLEDGE, doc, updates, actor.require_id())
        await self.audit(actor, f"knowledge_{payload.action}", record_id)
        return public(result)

    async def retrieve(self, question: str, language: str) -> list[dict[str, Any]]:
        cfg = await self.settings()
        today = utc_now().astimezone(ZoneInfo(cfg.timezone)).date().isoformat()
        query = {
            "status": "published",
            "language": language,
            "is_deleted": False,
            "$and": [
                {"$or": [{"effective_on": None}, {"effective_on": {"$lte": today}}]},
                {"$or": [{"expires_on": None}, {"expires_on": {"$gt": today}}]},
            ],
        }
        tokens = set(re.findall(r"\w{2,}", question.casefold()))
        ranked = []
        async for doc in self.db.voice_knowledge.find(query).limit(500):
            for chunk in doc["chunks"]:
                score = len(tokens & set(re.findall(r"\w{2,}", chunk.casefold())))
                if score:
                    ranked.append(
                        (
                            score,
                            {
                                "id": str(doc["_id"]),
                                "title": doc["title"],
                                "version": doc["version"],
                                "excerpt": chunk,
                            },
                        )
                    )
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [source for _, source in ranked[:5]]

    async def console(self, payload: ConsoleInput, actor: User) -> dict[str, Any]:
        # Include recent user context for short follow-ups such as "what documents?".
        context = " ".join(t["content"] for t in payload.history[-4:] if t["role"] == "user")
        sources = await self.retrieve(context + " " + payload.question, payload.language)
        await self.audit(actor, "retrieval_test")
        config = get_conversation_config()
        if config.local_ai_enabled and config.local_ai_model:
            cfg = await self.settings()
            try:
                answer = await LocalConversationAdapter(config).respond(
                    question=payload.question,
                    history=payload.history,
                    sources=sources,
                    instructions=cfg.conversation_instructions,
                    operational_rules=cfg.operational_rules,
                    language=payload.language,
                )
                return {
                    **answer,
                    "sources": sources,
                    "language": payload.language,
                    "mode": "local_dynamic_text",
                    "warnings": [
                        "Generated test response. Financial accuracy and language quality require review.",
                        "Text testing does not validate real-time audio or telephone calls.",
                    ],
                }
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                # Do not echo provider errors, source text or caller content into ordinary logs.
                return {
                    "response": None,
                    "sources": sources,
                    "language": payload.language,
                    "mode": "provider_unavailable",
                    "uncertain": True,
                    "warnings": [
                        "Local model unavailable or returned an invalid response. Offer human assistance."
                    ],
                }
        # Never turn keyword retrieval or a canned mock response into an alleged dynamic AI answer.
        return {
            "response": None,
            "sources": sources,
            "language": payload.language,
            "mode": "retrieval_only",
            "uncertain": True,
            "warnings": [
                "Dynamic AI model and streaming speech adapter are not configured.",
                "These are lexical retrieval candidates, not verified answers.",
            ],
        }

    async def require_live(self, feature: str, actor: User) -> None:
        await self.audit(actor, f"blocked_{feature}")
        raise ForbiddenError(
            "Live calling, recording and cloning are unavailable until verified adapters and prerequisites are implemented."
        )
