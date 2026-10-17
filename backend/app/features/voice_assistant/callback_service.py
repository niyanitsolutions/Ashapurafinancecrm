"""Confirmed callback extension of existing tasks. No telephony command is issued."""

import hashlib
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.access_control.repository import PermissionRepository
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.employee.repository import EmployeeRepository
from app.features.insurance_management.service import InsuranceCaseService
from app.features.leads.service import LeadService
from app.features.loan_management.service import LoanCaseService
from app.features.reminders.models import Task
from app.features.voice_assistant.access import owner_only
from app.features.voice_assistant.callback_schemas import CallbackAction, CallbackInput, EntityType
from app.features.voice_assistant.platform_service import PlatformService
from app.features.voice_assistant.scheduling import local_to_utc, next_window
from app.features.voice_assistant.service import VoiceService
from app.shared.audit_log import AuditLog
from app.utils.datetime import utc_now


async def ensure_callback_indexes(db: AsyncIOMotorDatabase[Any]) -> None:
    await db.tasks.create_index(
        [
            ("created_by", 1),
            ("voice_callback.environment", 1),
            ("voice_callback.idempotency_key", 1),
        ],
        unique=True,
        partialFilterExpression={"voice_callback.idempotency_key": {"$type": "string"}},
    )
    await db.tasks.create_index(
        [("voice_callback.environment", 1), ("voice_callback.contact_key", 1)],
        unique=True,
        partialFilterExpression={"voice_callback.active": True},
    )
    await db.tasks.create_index(
        [("voice_callback.active", 1), ("voice_callback.next_review_at", 1)]
    )
    await db.tasks.create_index("voice_callback.audit_pending")
    await db.tasks.create_index(
        [("related_entity_type", 1), ("related_entity_id", 1), ("created_at", -1)]
    )


def safe_callback(doc: dict[str, Any]) -> dict[str, Any]:
    callback = doc["voice_callback"]
    return {
        "id": str(doc["_id"]),
        "version": doc["version"],
        "due_at": doc["due_at"],
        "assigned_to": doc["assigned_to"],
        "entity_type": doc["related_entity_type"],
        "entity_id": doc["related_entity_id"],
        "calls_placed": 0,
        "history_count": callback["event_count"],
    } | {
        key: callback.get(key)
        for key in (
            "state",
            "environment",
            "timezone",
            "dst_fold",
            "requested_local",
            "customer_request",
            "customer_id",
            "provenance",
            "source_call_id",
            "blockers",
            "confirmed_at",
        )
    }


class CallbackService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.engine = PermissionEngine(db)

    async def permission(self, actor: User, module: str, resource: str, action: str) -> None:
        if actor.status != "active" or not await self.engine.has_permission(
            actor, module=module, resource=resource, action=action
        ):
            raise ForbiddenError("Required record, voice or task permission is unavailable.")

    async def entity(
        self, kind: EntityType, record_id: str, actor: User, action: str = "view"
    ) -> str | None:
        if kind == "lead":
            await self.permission(actor, "leads", "leads", action)
            lead = await LeadService(self.db).get_lead_scoped(record_id, actor)
            return lead.customer_id
        if kind == "loan_case":
            case = await LoanCaseService(self.db).get_case(record_id, actor)
            module = "loan_management"
        else:
            case = await InsuranceCaseService(self.db).get_case(record_id, actor)
            module = "insurance_management"
        resource = "applications"
        child = await PermissionRepository(self.db).find_by_module_resource(
            module, f"applications.{case.current_status}"
        )
        if child is not None and action in child.actions:
            resource = f"applications.{case.current_status}"
        await self.permission(actor, module, resource, action)
        return case.customer_id

    async def record(self, record_id: str, actor: User, action: str = "view") -> dict[str, Any]:
        await self.permission(actor, "voice_assistant", "calls", action)
        if not ObjectId.is_valid(record_id) or record_id != str(ObjectId(record_id)):
            raise NotFoundError("Callback not found.")
        doc = await self.db.tasks.find_one(
            {
                "_id": ObjectId(record_id),
                "is_deleted": False,
                "voice_callback.active": {"$exists": True},
            }
        )
        if doc is None:
            raise NotFoundError("Callback not found.")
        await self.entity(doc["related_entity_type"], doc["related_entity_id"], actor)
        if action != "view":
            await self.entity(doc["related_entity_type"], doc["related_entity_id"], actor, "edit")
            await self.permission(actor, "reminders", "tasks", "edit")
        # Same assignee boundary as existing reminders; entity scope is additional.
        if actor.role != "owner":
            employee = await EmployeeRepository(self.db).find_by_user_id(actor.require_id())
            if employee is None or doc["assigned_to"] != employee.require_id():
                raise ForbiddenError("Callback is assigned to another employee.")
        return cast(dict[str, Any], doc)

    async def list(
        self, kind: EntityType, entity_id: str, environment: str, actor: User, page: int = 1
    ) -> dict[str, Any]:
        await self.permission(actor, "voice_assistant", "calls", "view")
        await self.entity(kind, entity_id, actor)
        query: dict[str, Any] = {
            "is_deleted": False,
            "related_entity_type": kind,
            "related_entity_id": entity_id,
            "voice_callback.environment": environment,
        }
        if actor.role != "owner":
            employee = await EmployeeRepository(self.db).find_by_user_id(actor.require_id())
            if employee is None:
                raise ForbiddenError("Staff employee record is unavailable.")
            query["assigned_to"] = employee.require_id()
        docs = (
            await self.db.tasks.find(query, {"voice_callback.history": 0})
            .sort("created_at", -1)
            .skip((page - 1) * 25)
            .limit(25)
            .to_list(25)
        )
        editable = True
        try:
            await self.entity(kind, entity_id, actor, "edit")
        except ForbiddenError:
            editable = False
        current_employee = await EmployeeRepository(self.db).find_by_user_id(actor.require_id())
        capabilities = {
            "create": editable
            and await self.engine.has_permission(
                actor, module="voice_assistant", resource="calls", action="create"
            )
            and await self.engine.has_permission(
                actor, module="reminders", resource="tasks", action="create"
            ),
            "edit": editable
            and await self.engine.has_permission(
                actor, module="voice_assistant", resource="calls", action="edit"
            )
            and await self.engine.has_permission(
                actor, module="reminders", resource="tasks", action="edit"
            ),
            "current_employee_id": current_employee.require_id() if current_employee else None,
        }
        return {
            "items": [safe_callback(doc) for doc in docs],
            "total": await self.db.tasks.count_documents(query),
            "capabilities": capabilities,
            "live_dispatch": "blocked_unimplemented_native_transport",
        }

    async def create(self, payload: CallbackInput, actor: User) -> dict[str, Any]:
        await self.permission(actor, "voice_assistant", "calls", "create")
        await self.permission(actor, "voice_assistant", "calls", "view")
        await self.permission(actor, "reminders", "tasks", "create")
        customer = await self.entity(payload.entity_type, payload.entity_id, actor)
        if customer is not None and (
            not ObjectId.is_valid(customer) or customer != str(ObjectId(customer))
        ):
            raise ValidationError(
                "The CRM customer relationship needs staff review before scheduling."
            )
        await self.entity(payload.entity_type, payload.entity_id, actor, "edit")
        assignee = await EmployeeRepository(self.db).find_by_id(payload.assigned_to)
        if assignee is None or assignee.status != "active":
            raise ValidationError("Choose an active employee for callback supervision.")
        assignee_user = await UserRepository(self.db).find_by_id(assignee.user_id)
        if assignee_user is None or assignee_user.status != "active":
            raise ValidationError("The callback supervisor account is unavailable.")
        if actor.role != "owner" and assignee.user_id != actor.require_id():
            raise ForbiddenError("Employees can schedule only their own supervised callbacks.")
        key = {
            "created_by": actor.require_id(),
            "voice_callback.environment": payload.environment,
            "voice_callback.idempotency_key": payload.idempotency_key,
        }
        digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        existing = await self.db.tasks.find_one(key)
        if existing:
            if existing["voice_callback"]["input_hash"] != digest:
                raise ConflictError(
                    "Idempotency key was already used for a different callback request."
                )
            replay = await self.record(str(existing["_id"]), actor)
            await self.audit(actor.require_id(), "requested", str(existing["_id"]))
            return safe_callback(replay)
        if customer and await self.db.voice_contact_suppressions.find_one(
            {"customer_id": customer, "scope": "global", "suppressed": True}
        ):
            raise ForbiddenError(
                "Global voice do-not-call is active. A callback request cannot clear this restriction."
            )
        due = local_to_utc(payload.requested_local, payload.timezone, payload.dst_fold)
        if not utc_now() < due <= utc_now() + timedelta(days=366):
            raise ValidationError("Choose a future callback time within the next year.")
        if payload.source_call_id:
            call = await VoiceService(self.db).call(payload.source_call_id, actor)
            if (
                not customer
                or call.get("customer_id") != customer
                or call.get("provider") == "mock"
                or call.get("environment") != payload.environment
            ):
                raise ValidationError(
                    "Source call must have an authoritative matching CRM customer binding."
                )
        now = utc_now()
        callback = {
            "environment": payload.environment,
            "idempotency_key": payload.idempotency_key,
            "input_hash": digest,
            "customer_id": customer,
            "contact_key": f"customer:{customer}" if customer else f"lead:{payload.entity_id}",
            "active": True,
            "state": "awaiting_confirmation",
            "timezone": payload.timezone,
            "dst_fold": payload.dst_fold,
            "requested_local": payload.requested_local.isoformat(),
            "customer_request": payload.customer_request,
            "provenance": "staff_attested_customer_request_not_identity_verification",
            "source_call_id": payload.source_call_id,
            "next_review_at": due,
            "event_count": 1,
            "audit_pending": True,
            "history": [
                {
                    "event": "requested",
                    "receipt_id": uuid4().hex,
                    "at": now,
                    "actor_id": actor.require_id(),
                    "new_due_at": due,
                    "new_requested_local": payload.requested_local.isoformat(),
                    "new_timezone": payload.timezone,
                    "new_dst_fold": payload.dst_fold,
                    "request": payload.customer_request,
                    "source_call_id": payload.source_call_id,
                }
            ],
            "blockers": ["Customer time confirmation and live readiness required."],
        }
        task = Task(
            title="AI callback — verification required",
            description="Managed AI callback. Review the linked CRM record. No manual dialing; live automated calling remains blocked.",
            assigned_to=payload.assigned_to,
            assigned_by=actor.require_id(),
            due_at=due,
            related_entity_type=payload.entity_type,
            related_entity_id=payload.entity_id,
            created_by=actor.require_id(),
            voice_callback=callback,
        )
        doc = task.model_dump(by_alias=True, exclude={"id"})
        try:
            doc["_id"] = (await self.db.tasks.insert_one(doc)).inserted_id
        except DuplicateKeyError:
            retry = await self.db.tasks.find_one(key)
            if retry and retry["voice_callback"]["input_hash"] == digest:
                replay = await self.record(str(retry["_id"]), actor)
                await self.audit(actor.require_id(), "requested", str(retry["_id"]))
                return safe_callback(replay)
            raise ConflictError(
                "An active callback already exists for this contact, or this request was changed concurrently."
            ) from None
        await self.audit(actor.require_id(), "requested", str(doc["_id"]))
        stored = await self.db.tasks.find_one({"_id": doc["_id"]})
        assert stored is not None
        return safe_callback(stored)

    async def change(
        self, doc: dict[str, Any], fields: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, Any]:
        # State, due date and complete append-only history change in one task document.
        result = await self.db.tasks.find_one_and_update(
            {"_id": doc["_id"], "version": doc["version"], "is_deleted": False},
            {
                "$set": fields | {"updated_at": utc_now(), "voice_callback.audit_pending": True},
                "$inc": {"version": 1, "voice_callback.event_count": 1},
                "$push": {"voice_callback.history": event | {"receipt_id": uuid4().hex}},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise ConflictError("Callback changed. Refresh before retrying.")
        return cast(dict[str, Any], result)

    async def action(self, record_id: str, payload: CallbackAction, actor: User) -> dict[str, Any]:
        doc = await self.record(record_id, actor, "edit")
        callback = doc["voice_callback"]
        if doc["version"] != payload.version or not callback["active"]:
            raise ConflictError("Callback changed or is closed. Refresh before retrying.")
        if payload.action != "cancel" and callback["event_count"] >= 1000:
            raise ConflictError(
                "Callback history limit reached; cancel and obtain a reviewed new request."
            )
        if (
            payload.action != "cancel"
            and callback.get("customer_id")
            and await self.db.voice_contact_suppressions.find_one(
                {"customer_id": callback["customer_id"], "scope": "global", "suppressed": True}
            )
        ):
            raise ForbiddenError(
                "Global voice do-not-call is active. Cancel this callback or obtain authorized contact-policy review."
            )
        event = {
            "event": payload.action,
            "at": utc_now(),
            "actor_id": actor.require_id(),
            "reason": payload.reason,
            "old_due_at": doc["due_at"],
            "old_requested_local": callback["requested_local"],
            "old_timezone": callback["timezone"],
            "old_dst_fold": callback.get("dst_fold"),
        }
        fields: dict[str, Any] = {"updated_by": actor.require_id()}
        if payload.action == "cancel":
            fields |= {
                "voice_callback.state": "cancelled",
                "voice_callback.active": False,
                "status": "completed",
                "completed_at": utc_now(),
            }
        elif payload.action == "reschedule":
            assert payload.requested_local is not None and payload.timezone is not None
            due = local_to_utc(payload.requested_local, payload.timezone, payload.dst_fold)
            if not utc_now() < due <= utc_now() + timedelta(days=366):
                raise ValidationError("Choose a future callback time within the next year.")
            fields |= {
                "due_at": due,
                "voice_callback.requested_local": payload.requested_local.isoformat(),
                "voice_callback.timezone": payload.timezone,
                "voice_callback.dst_fold": payload.dst_fold,
                "voice_callback.state": "awaiting_confirmation",
                "voice_callback.confirmed_at": None,
                "voice_callback.next_review_at": due,
            }
            event["new_due_at"] = due
            event["new_requested_local"] = payload.requested_local.isoformat()
            event["new_timezone"] = payload.timezone
            event["new_dst_fold"] = payload.dst_fold
        elif payload.action == "confirm":
            if doc["due_at"] <= utc_now():
                raise ValidationError(
                    "Requested time has passed. Reschedule and obtain customer confirmation."
                )
            fields |= {
                "voice_callback.state": "scheduled",
                "voice_callback.confirmed_at": utc_now(),
                "voice_callback.confirmed_by": actor.require_id(),
                "voice_callback.blockers": [],
                "voice_callback.next_review_at": doc["due_at"],
            }
        else:
            if not callback.get("confirmed_at"):
                raise ValidationError(
                    "Customer time confirmation is required before readiness evaluation."
                )
            fields |= {
                "voice_callback.state": "scheduled",
                "voice_callback.next_review_at": doc["due_at"],
            }
        result = await self.change(doc, fields, event)
        await self.audit(actor.require_id(), payload.action, record_id)
        return safe_callback(result)

    async def history(self, record_id: str, actor: User, page: int) -> dict[str, Any]:
        doc = await self.record(record_id, actor)
        events = list(reversed(doc["voice_callback"]["history"]))
        return {"items": events[(page - 1) * 25 : page * 25], "total": len(events)}

    async def resolve_owner(self, record_id: str, payload: CallbackAction, actor: User) -> dict[str, Any]:
        """Terminal closure only, including deleted parents; never adopts authority."""
        owner_only(actor)
        await self.permission(actor, "reminders", "tasks", "edit")
        if payload.action != "cancel":
            raise ValidationError("Owner resolution only cancels; new scheduling requires current CRM access and confirmation.")
        if not ObjectId.is_valid(record_id) or record_id != str(ObjectId(record_id)):
            raise NotFoundError("Callback not found.")
        doc = await self.db.tasks.find_one({"_id": ObjectId(record_id), "is_deleted": False, "voice_callback.active": {"$exists": True}})
        if doc is None:
            raise NotFoundError("Callback not found.")
        if doc["version"] != payload.version or not doc["voice_callback"]["active"]:
            raise ConflictError("Callback changed or is closed. Refresh before resolving.")
        result = await self.change(doc, {
            "voice_callback.active": False, "voice_callback.state": "cancelled",
            "status": "completed", "completed_at": utc_now(), "updated_by": actor.require_id(),
        }, {
            "event": "owner_resolution_cancelled", "at": utc_now(),
            "actor_id": actor.require_id(), "reason": payload.reason,
            "prior_state": doc["voice_callback"]["state"], "calls_placed": 0,
        })
        await self.audit(actor.require_id(), "owner_resolution_cancelled", record_id)
        return {"id": record_id, "version": result["version"], "state": "cancelled", "calls_placed": 0}

    async def audit(self, actor_id: str, event: str, record_id: str) -> None:
        # The atomic Task history is the outbox. Project only events carrying a
        # receipt identity; never invent receipts for unknown historical writes.
        doc = await self.db.tasks.find_one({"_id": ObjectId(record_id)})
        if doc is None:
            return
        for saved in doc["voice_callback"]["history"]:
            receipt = saved.get("receipt_id")
            if not receipt:
                continue
            entry = AuditLog(
                event_type=f"voice_assistant.callback_{saved['event']}",
                user_id=saved.get("actor_id", "voice-worker"),
                created_at=saved["at"],
                metadata={"task_id": record_id, "callback_receipt_id": receipt},
            ).model_dump(by_alias=True, exclude={"id"})
            entry["_id"] = ObjectId(hashlib.sha256(f"callback:{record_id}:{receipt}".encode()).hexdigest()[:24])
            try:
                await self.db.audit_logs.insert_one(entry)
            except DuplicateKeyError:
                previous = await self.db.audit_logs.find_one({"_id": entry["_id"]})
                if not previous or any(previous.get(key) != entry[key] for key in ("metadata", "event_type", "user_id", "created_at")):
                    raise ConflictError("Callback audit receipt integrity check failed.") from None
        await self.db.tasks.update_one(
            {"_id": doc["_id"], "version": doc["version"]},
            {"$set": {"voice_callback.audit_pending": False}},
        )

    async def reconcile_audit(self) -> int:
        docs = await self.db.tasks.find({"voice_callback.audit_pending": True}, {"_id": 1}).limit(25).to_list(25)
        for doc in docs:
            await self.audit("voice-worker", "reconcile", str(doc["_id"]))
        return len(docs)

    async def sweep(self) -> int:
        await self.reconcile_audit()
        now = utc_now()
        query = {
            "is_deleted": False,
            "due_at": {"$lte": now},
            "voice_callback.active": True,
            "voice_callback.state": {"$in": ["scheduled", "blocked", "awaiting_confirmation", "confirmation_expired"]},
            "voice_callback.next_review_at": {"$lte": now},
        }
        docs = (
            await self.db.tasks.find(query, {"voice_callback.history": 0})
            .sort("voice_callback.next_review_at", 1)
            .limit(25)
            .to_list(25)
        )
        processed = 0
        for doc in docs:
            callback = doc["voice_callback"]
            actor = await UserRepository(self.db).find_by_id(doc["created_by"])
            blockers = []
            try:
                if actor is None or actor.status != "active":
                    raise ForbiddenError("Account unavailable.")
                await self.record(str(doc["_id"]), actor, "edit")
                supervisor = await EmployeeRepository(self.db).find_by_id(doc["assigned_to"])
                supervisor_user = (
                    await UserRepository(self.db).find_by_id(supervisor.user_id)
                    if supervisor
                    else None
                )
                if (
                    not supervisor
                    or supervisor.status != "active"
                    or not supervisor_user
                    or supervisor_user.status != "active"
                ):
                    raise ForbiddenError("Callback supervisor unavailable.")
                customer = await self.entity(
                    doc["related_entity_type"], doc["related_entity_id"], actor
                )
                if customer != callback.get("customer_id"):
                    blockers.append("crm_customer_binding_changed")
            except (ForbiddenError, NotFoundError, ValidationError):
                blockers.append("current_record_or_staff_authorization_failed")
            customer_id = callback.get("customer_id")
            suppressed = bool(
                customer_id
                and await self.db.voice_contact_suppressions.find_one(
                    {"customer_id": customer_id, "scope": "global", "suppressed": True}
                )
            )
            if not customer_id:
                blockers.append("authoritative_customer_and_voice_consent_required")
            elif not ObjectId.is_valid(customer_id):
                blockers.append("invalid_customer_binding")
            elif not await self.db.customers.find_one(
                {"_id": ObjectId(customer_id), "is_deleted": False, "status": "active"}, {"_id": 1}
            ):
                blockers.append("customer_inactive_or_unavailable")
            elif not await self.db.voice_contact_consents.find_one(
                {
                    "customer_id": customer_id,
                    "purpose": "callback",
                    "action": "grant",
                    "expires_at": {"$gt": now},
                }
            ):
                blockers.append("missing_or_expired_callback_consent")
            cfg = await VoiceService(self.db).settings()
            if (
                next_window(
                    now,
                    cfg.timezone,
                    cfg.calling_start,
                    cfg.calling_end,
                    [day.isoformat() for day in cfg.holidays],
                )
                != now
            ):
                blockers.append("outside_business_calling_window")
            platform = await PlatformService(self.db).record(callback["environment"])
            if (
                platform["emergency_stopped"]
                or not platform["outbound"]
                or not platform["processing"]
            ):
                blockers.append("live_directions_disabled_or_emergency_stop")
            if not platform["components"].get("callbacks", {}).get("enabled"):
                blockers.append("callback_automation_disabled")
            blockers.append("native_live_dispatch_and_number_authorization_unimplemented")
            blockers.append("live_callback_retry_and_contact_reservation_policy_unverified")
            state = (
                "opted_out"
                if suppressed
                else "confirmation_expired"
                if callback["state"] in {"awaiting_confirmation", "confirmation_expired"}
                else "blocked"
            )
            fields: dict[str, Any] = {
                "voice_callback.state": state,
                "voice_callback.blockers": ["contact_suppressed"] if suppressed else blockers,
                "voice_callback.next_review_at": now + timedelta(minutes=5),
            }
            # A revoked principal, missing parent or changed customer binding cannot
            # inherit authority on restore/restart. Close bookkeeping and release
            # the unique contact slot; retain the complete original request/history.
            lost_authority = any(reason in blockers for reason in (
                "current_record_or_staff_authorization_failed",
                "crm_customer_binding_changed",
                "customer_inactive_or_unavailable",
                "invalid_customer_binding",
            ))
            if lost_authority and not suppressed:
                state = "closed_ineligible"
                fields |= {
                    "voice_callback.state": state,
                    "voice_callback.active": False,
                    "status": "completed",
                    "completed_at": now,
                }
            if suppressed:
                fields |= {
                    "voice_callback.active": False,
                    "status": "completed",
                    "completed_at": now,
                }
            elif state == "confirmation_expired":
                fields["voice_callback.blockers"] = [
                    "Requested time passed without customer confirmation; reschedule and confirm explicitly."
                ]
            if callback["event_count"] >= 1000 and not suppressed:
                state = "closed_history_limit"
                fields |= {
                    "voice_callback.state": "closed_history_limit",
                    "voice_callback.active": False,
                    "status": "completed",
                    "completed_at": now,
                    "voice_callback.blockers": [
                        "History limit reached without placing any call; new reviewed request required."
                    ],
                }
            try:
                if (
                    callback.get("blockers") == fields["voice_callback.blockers"]
                    and callback["state"] == state
                ):
                    await self.db.tasks.update_one(
                        {"_id": doc["_id"], "version": doc["version"]},
                        {"$set": {"voice_callback.next_review_at": now + timedelta(minutes=5)}},
                    )
                else:
                    await self.change(
                        doc,
                        fields,
                        {
                            "event": state,
                            "at": now,
                            "source": "arq_readiness_only",
                            "calls_placed": 0,
                            "blockers": fields["voice_callback.blockers"],
                        },
                    )
                    await self.audit("voice-worker", state, str(doc["_id"]))
                processed += 1
            except ConflictError:
                continue
        return processed
