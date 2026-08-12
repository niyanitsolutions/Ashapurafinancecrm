"""Module 9C — Communication Engine business logic.

`Business Module -> Communication Service -> Queue -> Provider Adapter -> Provider ->
Delivery Status -> Communication History.` No frozen module (Leads, Customer, Workflow
Engine, Reminders, Referral Partner Management) is modified to call this engine
directly: `poll_business_events` scans each business event's already-written
`audit_logs` entry (the same pattern Module 6D established, decision 065) and resolves a
recipient using each frozen module's own existing, read-only repository classes.

OTP is deliberately excluded from this engine — Auth (Module 1) is frozen and OTP
delivery must stay synchronous; a queued, polled send would arrive too late to be
useful. `TemplateCategory.OTP` remains a reserved value only. See docs/COMMUNICATION.md.
"""

import json
from datetime import timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.communication import template_engine
from app.features.communication.adapters import ADAPTERS
from app.features.communication.constants import (
    AUDIT_EVENT_TYPE_BY_BUSINESS_EVENT,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MINUTES,
    TEMPLATE_CATEGORY_BY_EVENT,
    AuditEvent,
    BusinessEvent,
    Channel,
    QueueStatus,
)
from app.features.communication.models import (
    CommunicationHistory,
    CommunicationQueueItem,
    CommunicationTemplate,
    ProviderDeliveryLog,
)
from app.features.communication.repository import (
    CommunicationCheckpointRepository,
    CommunicationHistoryRepository,
    CommunicationQueueRepository,
    CommunicationTemplateRepository,
    ProviderDeliveryLogRepository,
)
from app.features.communication.schemas import CreateTemplateRequest, UpdateTemplateRequest
from app.features.customer.repository import ApplicationRepository, CustomerRepository
from app.features.employee.repository import EmployeeRepository
from app.features.referral_partner_management.repository import (
    CommissionEntryRepository,
    ReferralPartnerRepository,
)
from app.features.workflow_engine.repository import ApplicationWorkflowRepository
from app.security.encryption import decrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now


class CommunicationService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self._db = db
        self._templates = CommunicationTemplateRepository(db)
        self._queue = CommunicationQueueRepository(db)
        self._history = CommunicationHistoryRepository(db)
        self._delivery_logs = ProviderDeliveryLogRepository(db)
        self._checkpoints = CommunicationCheckpointRepository(db)
        self._users = UserRepository(db)
        self._employees = EmployeeRepository(db)
        self._customers = CustomerRepository(db)
        self._applications = ApplicationRepository(db)
        self._workflows = ApplicationWorkflowRepository(db)
        self._referral_partners = ReferralPartnerRepository(db)
        self._commission_entries = CommissionEntryRepository(db)

    # ================================================================== templates (Owner-authored, admin CRUD)

    async def create_template(self, payload: CreateTemplateRequest, actor: User) -> CommunicationTemplate:
        variables = template_engine.extract_variable_names(payload.body)
        template = CommunicationTemplate(
            name=payload.name, channel=payload.channel, category=payload.category, subject=payload.subject,
            body=payload.body, variables=variables, language=payload.language, created_by=actor.require_id(),
        )
        template_id = await self._templates.insert(template)
        await write_audit_log(self._db, event_type=AuditEvent.TEMPLATE_CREATED, user_id=actor.require_id(), metadata={"template_id": template_id})
        found = await self._templates.find_by_id(template_id)
        assert found is not None
        return found

    async def list_templates(
        self, *, channel: str | None, category: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationTemplate], int]:
        return await self._templates.search_and_filter(channel=channel, category=category, skip=skip, limit=limit, sort=sort)

    async def get_template(self, template_id: str) -> CommunicationTemplate:
        template = await self._templates.find_by_id(template_id)
        if template is None:
            raise NotFoundError("Communication template not found.")
        return template

    async def update_template(self, template_id: str, payload: UpdateTemplateRequest, actor: User) -> CommunicationTemplate:
        template = await self.get_template(template_id)
        updates = payload.model_dump(exclude_unset=True)
        if "body" in updates:
            updates["variables"] = template_engine.extract_variable_names(updates["body"])
        updated = await self._templates.update(template_id, updates, updated_by=actor.require_id()) if updates else template
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.TEMPLATE_UPDATED, user_id=actor.require_id(), metadata={"template_id": template_id})
        return updated

    # ================================================================== queue + history (admin read + retry)

    async def list_queue(
        self, *, status: str | None, channel: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationQueueItem], int]:
        return await self._queue.search_and_filter(status=status, channel=channel, skip=skip, limit=limit, sort=sort)

    async def list_history(
        self, *, status: str | None, channel: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None
    ) -> tuple[list[CommunicationHistory], int]:
        return await self._history.search_and_filter(status=status, channel=channel, skip=skip, limit=limit, sort=sort)

    async def retry_message_now(self, queue_item_id: str, actor: User) -> CommunicationQueueItem:
        item = await self._queue.find_by_id(queue_item_id)
        if item is None:
            raise NotFoundError("Queue item not found.")
        if item.status not in (QueueStatus.FAILED, QueueStatus.EXHAUSTED):
            raise ValidationError("Only a failed or exhausted message can be retried.")
        await self._queue.update(queue_item_id, {"status": QueueStatus.PENDING, "next_retry_at": None, "error_detail": None})
        await write_audit_log(self._db, event_type=AuditEvent.MESSAGE_RETRIED, user_id=actor.require_id(), metadata={"queue_item_id": queue_item_id, "manual": True})
        await self._send_one(queue_item_id)
        updated = await self._queue.find_by_id(queue_item_id)
        assert updated is not None
        return updated

    async def send_now(self, *, channel: str, recipient: str, category: str, variables: dict[str, str], actor: User | None = None) -> bool:
        """Synchronous, immediate send — for a UI action that needs to send right now
        (e.g. the Secure Application Link "Share"/"Notify Customer" buttons), not the
        business-event queue/poller. A deliberate, narrow exception to "no frozen module
        calls this engine directly" (see this module's own docstring) — reuses the exact
        same template-render + adapter-dispatch path `_send_one` uses for queued
        messages, just without waiting for the next poll tick, so there is no duplicated
        send logic. Returns False (not an error) if no active template exists for this
        category/channel yet — same "nothing to send" semantics as `_enqueue`.
        """
        template = await self._templates.find_active_by_category_and_channel(category=category, channel=channel)
        if template is None:
            return False
        rendered_body = template_engine.render(template.body, variables)
        rendered_subject = template_engine.render(template.subject, variables) if template.subject else None
        item = CommunicationQueueItem(
            channel=channel, recipient=recipient, template_id=template.require_id(), variables=variables,
            rendered_subject=rendered_subject, rendered_body=rendered_body, entity_type="secure_link",
        )
        queue_item_id = await self._queue.insert(item)
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_ENQUEUED, user_id=actor.require_id() if actor else None,
            metadata={"queue_item_id": queue_item_id, "channel": channel, "category": category},
        )
        await self._send_one(queue_item_id)
        sent_item = await self._queue.find_by_id(queue_item_id)
        return sent_item is not None and sent_item.status == QueueStatus.SENT

    # ================================================================== enqueue (internal — the one funnel every trigger uses)

    async def _enqueue(
        self, *, business_event: str, entity_type: str, entity_id: str, channel: str, recipient: str, category: str, variables: dict[str, str]
    ) -> None:
        existing = await self._queue.find_existing_for_event(business_event=business_event, entity_type=entity_type, entity_id=entity_id, channel=channel)
        if existing is not None:
            return  # already enqueued for this (event, entity, channel) — never a duplicate send
        template = await self._templates.find_active_by_category_and_channel(category=category, channel=channel)
        if template is None:
            return  # no Owner-authored template yet for this category/channel — nothing to send, not an error
        rendered_body = template_engine.render(template.body, variables)
        rendered_subject = template_engine.render(template.subject, variables) if template.subject else None
        item = CommunicationQueueItem(
            channel=channel, recipient=recipient, template_id=template.require_id(), variables=variables,
            rendered_subject=rendered_subject, rendered_body=rendered_body, business_event=business_event,
            entity_type=entity_type, entity_id=entity_id,
        )
        queue_item_id = await self._queue.insert(item)
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_ENQUEUED, user_id=None,
            metadata={"queue_item_id": queue_item_id, "business_event": business_event, "channel": channel},
        )

    # ================================================================== recipient resolution (read-only against frozen modules)

    async def _resolve_user_contact(self, user_id: str) -> tuple[str | None, str | None]:
        """mobile, email — dispatches on the user's role since email lives on the
        role-specific profile (Employee/Customer/ReferralPartner), never on the shared
        `users` collection itself (Module 1, frozen — `User` has no email field)."""
        user = await self._users.find_by_id(user_id)
        if user is None:
            return None, None
        mobile = user.mobile
        if user.role == "employee":
            employee = await self._employees.find_by_user_id(user_id)
            return mobile, employee.email if employee else None
        if user.role == "customer":
            customer = await self._customers.find_by_user_id(user_id)
            return mobile, customer.email if customer else None
        if user.role == "referral_partner":
            partner = await self._referral_partners.find_by_user_id(user_id)
            return mobile, partner.email if partner else None
        return mobile, None  # owner — no email on file for this role yet

    async def _entity_ref_and_contact(
        self, business_event: str, metadata: dict[str, Any], audit_user_id: str | None
    ) -> tuple[str, str, str | None, str | None] | None:
        """Returns (entity_type, entity_id, mobile, email) for the one recipient this
        business event notifies, or None if it can't be resolved (e.g. a dangling
        reference, or an event whose metadata this poller doesn't recognize) — such rows
        are simply skipped."""
        if business_event == BusinessEvent.LEAD_ASSIGNED:
            lead_id = metadata.get("lead_id")
            employee_id = metadata.get("employee_id")
            if not lead_id or not employee_id:
                return None
            employee = await self._employees.find_by_id(employee_id)
            if employee is None:
                return None
            return "lead", str(lead_id), employee.mobile, employee.email

        if business_event == BusinessEvent.REMINDER_TRIGGERED:
            entity_type = metadata.get("entity_type")
            entity_id = metadata.get("entity_id")
            if not entity_type or not entity_id or not audit_user_id:
                return None
            mobile, email = await self._resolve_user_contact(audit_user_id)
            if mobile is None and email is None:
                return None
            return str(entity_type), str(entity_id), mobile, email

        if business_event == BusinessEvent.APPLICATION_SUBMITTED:
            application_id = metadata.get("application_id")
            if not application_id:
                return None
            application = await self._applications.find_by_id(application_id)
            if application is None:
                return None
            customer = await self._customers.find_by_user_id(application.user_id)
            if customer is None:
                return None
            return "application", str(application_id), customer.mobile, customer.email

        if business_event == BusinessEvent.DOCUMENT_REQUESTED:
            case_id = metadata.get("application_workflow_id")
            if not case_id:
                return None
            case = await self._workflows.find_by_id(case_id)
            if case is None:
                return None
            customer = await self._customers.find_by_id(case.customer_id)
            if customer is None:
                return None
            return "application_workflow", str(case_id), customer.mobile, customer.email

        if business_event == BusinessEvent.COMMISSION_READY:
            entry_id = metadata.get("entry_id")
            if not entry_id:
                return None
            entry = await self._commission_entries.find_by_id(entry_id)
            if entry is None:
                return None
            partner = await self._referral_partners.find_by_id(entry.partner_id)
            if partner is None:
                return None
            return "commission_entry", str(entry_id), partner.mobile, partner.email

        return None

    @staticmethod
    def _variables_for_event(metadata: dict[str, Any]) -> dict[str, str]:
        """Best-effort — whatever identifiers the audit metadata itself carries, passed
        straight through as template variables. A template author picks which of these
        (if any) to reference in `{{variable_name}}` form; none are required."""
        return {key: str(value) for key, value in metadata.items() if value is not None}

    # ================================================================== business event polling (worker-driven)

    async def poll_business_events(self) -> None:
        for business_event, audit_event_type in AUDIT_EVENT_TYPE_BY_BUSINESS_EVENT.items():
            since = await self._checkpoints.get_last_processed_at(business_event)
            query: dict[str, Any] = {"event_type": audit_event_type}
            if since is not None:
                query["created_at"] = {"$gt": since}
            cursor = self._db["audit_logs"].find(query).sort("created_at", 1).limit(500)
            latest_seen = since

            async for doc in cursor:
                metadata = doc.get("metadata") or {}
                latest_seen = doc["created_at"]

                if business_event == BusinessEvent.REMINDER_TRIGGERED and metadata.get("notification_type") != "reminder_triggered":
                    continue  # notification_created is shared by several notification types — only this one maps here

                resolved = await self._entity_ref_and_contact(business_event, metadata, doc.get("user_id"))
                if resolved is None:
                    continue
                entity_type, entity_id, mobile, email = resolved
                category = TEMPLATE_CATEGORY_BY_EVENT[business_event]
                variables = self._variables_for_event(metadata)

                if mobile:
                    await self._enqueue(
                        business_event=business_event, entity_type=entity_type, entity_id=entity_id,
                        channel=Channel.WHATSAPP, recipient=mobile, category=category, variables=variables,
                    )
                    await self._enqueue(
                        business_event=business_event, entity_type=entity_type, entity_id=entity_id,
                        channel=Channel.SMS, recipient=mobile, category=category, variables=variables,
                    )
                if email:
                    await self._enqueue(
                        business_event=business_event, entity_type=entity_type, entity_id=entity_id,
                        channel=Channel.EMAIL, recipient=email, category=category, variables=variables,
                    )

            if latest_seen is not None:
                await self._checkpoints.set_last_processed_at(business_event, latest_seen)

    # ================================================================== queue processing + retry (worker-driven)

    async def _active_config(self, channel: str) -> dict[str, Any] | None:
        return await self._db["integration_configs"].find_one({"integration_type": channel, "is_active": True, "is_deleted": False})

    async def _send_one(self, queue_item_id: str) -> None:
        item = await self._queue.find_by_id(queue_item_id)
        if item is None:
            return
        await self._queue.update(queue_item_id, {"status": QueueStatus.PROCESSING})

        config_doc = await self._active_config(item.channel)
        template = await self._templates.find_by_id(item.template_id)
        template_name = template.name if template else "(deleted template)"

        if config_doc is None:
            await self._finalize_failure(item, provider="(none)", error=f"No active {item.channel} integration is configured.", is_transient=False, template_name=template_name)
            return

        decrypted: dict[str, str] = json.loads(decrypt(config_doc["config_encrypted"])) if config_doc.get("config_encrypted") else {}
        adapter = ADAPTERS[item.channel]
        outcome = await adapter(recipient=item.recipient, subject=item.rendered_subject, body=item.rendered_body, config=decrypted)

        await self._delivery_logs.insert(
            ProviderDeliveryLog(
                queue_item_id=queue_item_id, channel=item.channel, provider=config_doc.get("provider", "unknown"),
                attempt_number=item.retry_count + 1, success=outcome.success, provider_message_id=outcome.provider_message_id,
                error=outcome.error, response_time_ms=outcome.response_time_ms, attempted_at=utc_now(),
            )
        )

        if outcome.success:
            sent_at = utc_now()
            await self._queue.update(queue_item_id, {"status": QueueStatus.SENT, "sent_at": sent_at, "provider_message_id": outcome.provider_message_id, "error_detail": None})
            await write_audit_log(self._db, event_type=AuditEvent.MESSAGE_SENT, user_id=None, metadata={"queue_item_id": queue_item_id, "channel": item.channel})
            await self._upsert_history(item, provider=config_doc.get("provider", "unknown"), template_name=template_name, status=QueueStatus.SENT, error=None, sent_at=sent_at, retry_count=item.retry_count)
            return

        if not outcome.is_transient:
            await self._finalize_failure(item, provider=config_doc.get("provider", "unknown"), error=outcome.error, is_transient=False, template_name=template_name)
            return

        retry_count = item.retry_count + 1
        if retry_count >= MAX_RETRY_ATTEMPTS:
            await self._finalize_failure(item, provider=config_doc.get("provider", "unknown"), error=outcome.error, is_transient=True, template_name=template_name, retry_count=retry_count)
            return

        next_retry_at = utc_now() + timedelta(minutes=RETRY_BACKOFF_MINUTES * (2**retry_count))
        await self._queue.update(queue_item_id, {"status": QueueStatus.RETRYING, "retry_count": retry_count, "next_retry_at": next_retry_at, "error_detail": outcome.error})

    async def _finalize_failure(
        self, item: CommunicationQueueItem, *, provider: str, error: str | None, is_transient: bool, template_name: str, retry_count: int | None = None
    ) -> None:
        status = QueueStatus.EXHAUSTED if is_transient else QueueStatus.FAILED
        updates: dict[str, Any] = {"status": status, "error_detail": error}
        if retry_count is not None:
            updates["retry_count"] = retry_count
        await self._queue.update(item.require_id(), updates)
        await write_audit_log(self._db, event_type=AuditEvent.MESSAGE_FAILED, user_id=None, metadata={"queue_item_id": item.require_id(), "channel": item.channel, "status": status})
        await self._upsert_history(item, provider=provider, template_name=template_name, status=status, error=error, sent_at=None, retry_count=retry_count if retry_count is not None else item.retry_count)

    async def _upsert_history(
        self, item: CommunicationQueueItem, *, provider: str, template_name: str, status: str, error: str | None, sent_at: Any, retry_count: int
    ) -> None:
        queue_item_id = item.require_id()
        existing = await self._history.find_by_queue_item(queue_item_id)
        fields: dict[str, Any] = {
            "queue_item_id": queue_item_id, "channel": item.channel, "provider": provider, "recipient": item.recipient,
            "template_id": item.template_id, "template_name": template_name, "variables": item.variables,
            "status": status, "error": error, "sent_at": sent_at, "delivered_at": None, "retry_count": retry_count,
        }
        if existing is None:
            await self._history.insert(CommunicationHistory(**fields))
        else:
            await self._history.update(existing.require_id(), fields)

    async def process_pending_queue(self) -> None:
        due = await self._queue.find_due_pending(limit=200)
        for item in due:
            await self._send_one(item.require_id())

    async def process_retry_queue(self) -> None:
        due = await self._queue.find_due_for_retry(now=utc_now(), limit=200)
        for item in due:
            await self._send_one(item.require_id())
