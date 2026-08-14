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

import hmac
import json
from datetime import timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.features.access_control.permission_engine import PermissionEngine
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.communication import template_engine
from app.features.communication.adapters import ADAPTERS, DeliveryOutcome
from app.features.communication.constants import (
    AUDIT_EVENT_TYPE_BY_BUSINESS_EVENT,
    BULK_ENQUEUE_BATCH_SIZE,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MINUTES,
    TEMPLATE_CATEGORY_BY_EVENT,
    AuditEvent,
    BulkMessageJobStatus,
    BusinessEvent,
    Channel,
    QueueStatus,
)
from app.features.communication.models import (
    BulkMessageJob,
    CommunicationHistory,
    CommunicationQueueItem,
    CommunicationTemplate,
    ProviderDeliveryLog,
)
from app.features.communication.repository import (
    BulkMessageJobRepository,
    CommunicationCheckpointRepository,
    CommunicationHistoryRepository,
    CommunicationQueueRepository,
    CommunicationTemplateRepository,
    ProviderDeliveryLogRepository,
)
from app.features.communication.schemas import CreateTemplateRequest, UpdateTemplateRequest
from app.features.customer.models import Customer
from app.features.customer.repository import ApplicationRepository, CustomerRepository
from app.features.employee.repository import EmployeeRepository
from app.features.leads.models import Lead
from app.features.leads.repository import LeadRepository
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
        self._leads = LeadRepository(db)
        self._bulk_jobs = BulkMessageJobRepository(db)

    # ================================================================== templates (Owner-authored, admin CRUD)

    async def create_template(self, payload: CreateTemplateRequest, actor: User) -> CommunicationTemplate:
        variables = template_engine.extract_variable_names(payload.body)
        template = CommunicationTemplate(
            name=payload.name, channel=payload.channel, category=payload.category, subject=payload.subject,
            body=payload.body, variables=variables, language=payload.language, created_by=actor.require_id(),
            provider_template_name=payload.provider_template_name, provider_template_namespace=payload.provider_template_namespace,
            provider_template_language=payload.provider_template_language,
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

    async def send_now(
        self, *, channel: str, recipient: str, variables: dict[str, str], entity_type: str, entity_id: str,
        category: str | None = None, template_id: str | None = None, actor: User | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Synchronous, immediate send — for a UI action that needs to send right now
        (the Secure Application Link "Share"/"Notify Customer" buttons, and Stage 3's
        Lead/Customer "Send Message" action), not the business-event queue/poller. A
        deliberate, narrow exception to "no frozen module calls this engine directly"
        (see this module's own docstring) — reuses the exact same template-render +
        adapter-dispatch path `_send_one` uses for queued messages, just without waiting
        for the next poll tick, so there is no duplicated send logic.

        Exactly one of `category` (resolves the single active template for that
        category+channel — the original, business-event-shaped usage) or `template_id`
        (an Owner/staff explicitly picked this exact template — Stage 3's usage) must be
        given. `entity_type`/`entity_id` are always required (generalized in Stage 3 —
        every prior call site already had a real entity to attribute the message to;
        `notify_secure_link`, the one pre-existing caller, was updated to pass the Lead's
        own id instead of the placeholder `"secure_link"` type it used before).

        Returns `(success, queue_item_id, error_message)` — `queue_item_id` is set even
        on failure (the item still exists, just not `sent`) so a caller can link to it;
        `error_message` surfaces the real reason (e.g. "MSG91 is not configured for this
        channel.") rather than a bare boolean, for a caller that needs to show it (Stage
        3's Send Message action does; `notify_secure_link` still only needs the boolean).
        """
        if bool(category) == bool(template_id):
            raise ValidationError("Provide exactly one of category or template_id.")

        if template_id:
            template = await self._templates.find_by_id(template_id)
            if template is None or template.status != "active" or template.channel != channel:
                return False, None, "Message template is invalid or not approved."
        else:
            assert category is not None  # narrowed by the mutual-exclusion check above
            template = await self._templates.find_active_by_category_and_channel(category=category, channel=channel)
            if template is None:
                return False, None, "Message template is invalid or not approved."

        rendered_body = template_engine.render(template.body, variables)
        rendered_subject = template_engine.render(template.subject, variables) if template.subject else None
        item = CommunicationQueueItem(
            channel=channel, recipient=recipient, template_id=template.require_id(), variables=variables,
            rendered_subject=rendered_subject, rendered_body=rendered_body, entity_type=entity_type, entity_id=entity_id,
        )
        queue_item_id = await self._queue.insert(item)
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_ENQUEUED, user_id=actor.require_id() if actor else None,
            metadata={"queue_item_id": queue_item_id, "channel": channel, "entity_type": entity_type, "entity_id": entity_id},
        )
        await self._send_one(queue_item_id)
        sent_item = await self._queue.find_by_id(queue_item_id)
        if sent_item is None:
            return False, queue_item_id, "Unexpected error while sending."
        success = sent_item.status == QueueStatus.SENT
        return success, queue_item_id, (None if success else sent_item.error_detail)

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
        # Threaded to the adapter so a provider-specific branch (currently only MSG91) can
        # dispatch without the queue processor itself ever branching on provider identity —
        # see communication/adapters.py's own module docstring.
        decrypted["_provider"] = config_doc.get("provider", "")
        adapter = ADAPTERS[item.channel]
        # Config-level whatsapp_template_* (set on the Communication Providers screen, Stage
        # 4 UI hardening) are only a fallback default — a template's own provider_template_*
        # (Stage 2) always wins when set, so per-template overrides keep working unchanged.
        provider_template_meta = (
            {
                "name": template.provider_template_name or decrypted.get("whatsapp_template_name"),
                "namespace": template.provider_template_namespace or decrypted.get("whatsapp_template_namespace"),
                "language": template.provider_template_language or decrypted.get("whatsapp_template_language"),
            }
            if template is not None
            else None
        )
        try:
            outcome = await adapter(
                recipient=item.recipient, subject=item.rendered_subject, body=item.rendered_body, config=decrypted,
                variables=item.variables, variable_order=template.variables if template is not None else None, provider_template_meta=provider_template_meta,
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad: an adapter must never be able to crash the queue processor
            # A production-blocking bug found during Stage 4 verification: an adapter can
            # raise an exception the old code never caught (e.g. Python's own `email`
            # package rejects a Subject/From/To header containing an embedded CR/LF —
            # `email.errors.HeaderParseError`, neither an OSError nor an SMTPException —
            # which a Lead/Customer's own `full_name` can contain today, nothing validates
            # against control characters at the model layer). Uncaught, this aborted the
            # entire `process_pending_queue`/`process_retry_queue` loop for that worker
            # tick (every other due item in the same batch silently skipped that tick) and
            # left this one item stranded in PROCESSING forever (`find_due_pending` only
            # ever queries `status=PENDING`, so a PROCESSING item is never picked up
            # again). Bulk Messaging (Stage 3) made this materially more likely to trigger
            # in practice (many customer-supplied names flowing through automatically,
            # unattended) — same class of finding this codebase already documents for
            # "never expose raw provider stack traces" (Part 16); the message is
            # truncated, not the raw traceback.
            outcome = DeliveryOutcome(False, None, str(exc)[:300], is_transient=False)

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
        self, item: CommunicationQueueItem, *, provider: str, template_name: str, status: str, error: str | None, sent_at: Any,
        retry_count: int, delivered_at: Any = None,
    ) -> None:
        queue_item_id = item.require_id()
        existing = await self._history.find_by_queue_item(queue_item_id)
        fields: dict[str, Any] = {
            "queue_item_id": queue_item_id, "channel": item.channel, "provider": provider, "recipient": item.recipient,
            "template_id": item.template_id, "template_name": template_name, "variables": item.variables,
            "status": status, "error": error, "sent_at": sent_at, "delivered_at": delivered_at, "retry_count": retry_count,
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

    # ================================================================== delivery webhook (Stage 2 — MSG91 DLR)

    async def verify_msg91_webhook_secret(self, provided_secret: str | None) -> bool:
        """A shared secret (Owner-chosen, stored on either the SMS or WhatsApp MSG91
        `IntegrationConfig`, appended as `?secret=` on the URL configured in MSG91's own
        dashboard) — MSG91 does not document a cryptographic webhook signature scheme
        (no HMAC header was found in official docs), so this is the honest, standard
        fallback for a provider without one: a secret embedded in the URL itself, the
        same posture Meta's own `webhook_verify_token` has for its GET handshake, just
        applied here to every POST instead of a one-time verification step."""
        if not provided_secret:
            return False
        for channel in (Channel.SMS, Channel.WHATSAPP):
            config_doc = await self._active_config(channel)
            if config_doc is None or config_doc.get("provider") != "msg91" or not config_doc.get("config_encrypted"):
                continue
            decrypted: dict[str, str] = json.loads(decrypt(config_doc["config_encrypted"]))
            stored_secret = decrypted.get("webhook_secret")
            # Constant-time comparison (Stage 4 hardening) — a plain `==` on a secret
            # leaks timing information proportional to the matching-prefix length; found
            # during the Stage 4 security review, fixed here since it's this exact
            # webhook's own comparison, not an unrelated file.
            if stored_secret and hmac.compare_digest(stored_secret, provided_secret):
                return True
        return False

    async def process_delivery_webhook(self, *, provider: str, provider_message_id: str, delivered: bool, failed: bool, error: str | None) -> str:
        """Idempotent — a duplicate or out-of-order callback for the same
        `provider_message_id` is a safe no-op, never a duplicate state transition or a
        duplicate `CommunicationHistory` row (`_upsert_history` always updates the same
        row in place). Returns a short outcome string for the caller to log, never raises
        for a business-logic reason (unknown message id is expected/benign, not an error).
        """
        item = await self._queue.find_by_provider_message_id(provider_message_id)
        if item is None:
            return "unknown_message_id"
        if item.status in (QueueStatus.DELIVERED, QueueStatus.FAILED, QueueStatus.EXHAUSTED):
            return "already_terminal"  # duplicate callback, or a later state this webhook must never regress
        if item.status != QueueStatus.SENT:
            return "unexpected_state"  # a DLR for a message not yet marked sent (still pending/processing/retrying) — ignore rather than corrupt state

        template = await self._templates.find_by_id(item.template_id)
        template_name = template.name if template else "(deleted template)"

        if delivered:
            delivered_at = utc_now()
            await self._queue.update(item.require_id(), {"status": QueueStatus.DELIVERED, "delivered_at": delivered_at})
            await self._upsert_history(
                item, provider=provider, template_name=template_name, status=QueueStatus.DELIVERED, error=None,
                sent_at=item.sent_at, retry_count=item.retry_count, delivered_at=delivered_at,
            )
            await write_audit_log(
                self._db, event_type=AuditEvent.MESSAGE_DELIVERED, user_id=None,
                metadata={"queue_item_id": item.require_id(), "provider_message_id": provider_message_id, "provider": provider},
            )
            return "marked_delivered"

        if failed:
            await self._queue.update(item.require_id(), {"status": QueueStatus.FAILED, "error_detail": error})
            await self._upsert_history(
                item, provider=provider, template_name=template_name, status=QueueStatus.FAILED, error=error,
                sent_at=item.sent_at, retry_count=item.retry_count,
            )
            await write_audit_log(
                self._db, event_type=AuditEvent.MESSAGE_FAILED, user_id=None,
                metadata={"queue_item_id": item.require_id(), "provider_message_id": provider_message_id, "provider": provider, "via": "webhook"},
            )
            return "marked_failed"

        return "unrecognized_status"

    # ================================================================== CRM record messaging (Stage 3)
    #
    # Recipient resolution + authorization/IDOR checks are read-only, independent
    # re-implementations of Lead's `LeadService.get_lead_scoped` and Customer's
    # `CustomerService.get_customer_for_staff` (both frozen) — NOT imports of those
    # services. `customer.service` already imports `CommunicationService` (the Secure
    # Application Link flow), so importing `CustomerService` back here would be a
    # circular import; the same choice was made for Lead for consistency, even though
    # `leads.service` itself has no such cycle. Must be kept in sync with those two
    # methods' own rules if either ever changes — see docs/decisions/DECISIONS.md.

    async def _acting_employee_id(self, actor: User) -> str | None:
        if actor.role != "employee":
            return None
        employee = await self._employees.find_by_user_id(actor.require_id())
        return employee.require_id() if employee else None

    async def _resolve_lead_for_message(self, lead_id: str, actor: User) -> Lead:
        if actor.role != OWNER:
            allowed = await PermissionEngine(self._db).has_permission(actor, module="leads", resource="leads", action="view")
            if not allowed:
                raise ForbiddenError("Missing permission: leads:leads:view")
        lead = await self._leads.find_by_id(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        if actor.role != OWNER:
            employee_id = await self._acting_employee_id(actor)
            if employee_id is None or lead.assigned_to != employee_id:
                raise ForbiddenError("This lead isn't assigned to you.")
        return lead

    async def _resolve_customer_for_message(self, customer_id: str, actor: User) -> Customer:
        if actor.role not in (OWNER, "employee"):
            raise ForbiddenError("This action is restricted to Owner/Employee.")
        customer = await self._customers.find_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        if actor.role != OWNER:
            employee_id = await self._acting_employee_id(actor)
            has_assignment = await self._applications.find_many({"customer_id": customer_id, "assigned_to": employee_id}, limit=1)
            if not has_assignment:
                raise ForbiddenError("This customer isn't assigned to you.")
        return customer

    async def send_crm_message(
        self, *, entity_type: str, entity_id: str, channel: str, template_id: str, actor: User, extra_variables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """The "Send Message" action on a Lead/Customer detail page. The recipient
        address is always resolved server-side from the authorized Lead/Customer record
        — a caller can never supply an arbitrary phone number/email to redirect a
        message (see this method's own IDOR checks above)."""
        if channel not in Channel.ALL:
            raise ValidationError(f"Unsupported channel '{channel}'.")

        if entity_type == "lead":
            lead = await self._resolve_lead_for_message(entity_id, actor)
            display_name, mobile, email = lead.full_name, lead.mobile, lead.email
        elif entity_type == "customer":
            customer = await self._resolve_customer_for_message(entity_id, actor)
            display_name, mobile, email = customer.full_name, customer.mobile, customer.email
        else:
            raise ValidationError(f"Sending a message is not supported for entity_type '{entity_type}'.")

        recipient = mobile if channel in (Channel.WHATSAPP, Channel.SMS) else email
        if not recipient:
            return False, None, "Invalid recipient."

        variables = {"customer_name": display_name, "mobile": mobile or "", "email": email or ""}
        variables.update(extra_variables or {})

        return await self.send_now(
            channel=channel, recipient=recipient, variables=variables, entity_type=entity_type, entity_id=entity_id,
            template_id=template_id, actor=actor,
        )

    async def list_messages_for_entity(self, *, entity_type: str, entity_id: str, actor: User) -> list[CommunicationQueueItem]:
        """The Messages panel on a Lead/Customer detail page — same IDOR scoping as
        sending, so a message can never be browsed for a record the caller can't access."""
        if entity_type == "lead":
            await self._resolve_lead_for_message(entity_id, actor)
        elif entity_type == "customer":
            await self._resolve_customer_for_message(entity_id, actor)
        else:
            raise ValidationError(f"Message history is not supported for entity_type '{entity_type}'.")
        return await self._queue.find_for_entity(entity_type=entity_type, entity_id=entity_id)

    # ================================================================== bulk messaging (Stage 3)
    #
    # Recipients are resolved by the caller (the Bulk Messages composer reuses the
    # existing, already-authorized `GET /leads`/`GET /customers` staff search endpoints
    # — no new filter-query engine, no change to Leads/Customer). This service only ever
    # sees an already-chosen `recipient_ids` list, deduplicated here and validated
    # per-id (existence + a contact method) at enqueue time — never trusted blindly.
    #
    # Bulk sending is intentionally NOT per-recipient IDOR-scoped like `send_crm_message`
    # — a "Filtered Leads"/"Selected Leads" campaign is inherently a cross-assignment,
    # feature-level action (an Owner/manager broadcasting to many records at once), gated
    # by the `communication:bulk:create` permission itself rather than each individual
    # recipient's own assignment. See docs/decisions/DECISIONS.md.

    async def create_bulk_message_job(
        self, *, channel: str, template_id: str, recipient_type: str, recipient_ids: list[str], actor: User,
    ) -> BulkMessageJob:
        if channel not in Channel.ALL:
            raise ValidationError(f"Unsupported channel '{channel}'.")
        if recipient_type not in ("lead", "customer"):
            raise ValidationError(f"Unsupported recipient_type '{recipient_type}'.")
        template = await self._templates.find_by_id(template_id)
        if template is None or template.status != "active" or template.channel != channel:
            raise ValidationError("Message template is invalid or not approved.")

        deduped_ids = list(dict.fromkeys(recipient_ids))  # preserves order, drops duplicates
        if not deduped_ids:
            raise ValidationError("No recipients selected.")

        job = BulkMessageJob(
            channel=channel, template_id=template_id, recipient_type=recipient_type, recipient_ids=deduped_ids, created_by=actor.require_id(),
        )
        job_id = await self._bulk_jobs.insert(job)
        await write_audit_log(
            self._db, event_type=AuditEvent.BULK_JOB_CREATED, user_id=actor.require_id(),
            metadata={"bulk_job_id": job_id, "channel": channel, "template_id": template_id, "recipient_count": len(deduped_ids)},
        )
        created = await self._bulk_jobs.find_by_id(job_id)
        assert created is not None
        return created

    async def get_bulk_message_job(self, job_id: str) -> BulkMessageJob:
        job = await self._bulk_jobs.find_by_id(job_id)
        if job is None:
            raise NotFoundError("Bulk message job not found.")
        return job

    async def bulk_job_progress(self, job_id: str) -> dict[str, int]:
        await self.get_bulk_message_job(job_id)  # 404s if the job doesn't exist
        counts = await self._queue.status_counts_for_business_event(f"bulk:{job_id}")
        sent = counts.get(QueueStatus.SENT, 0) + counts.get(QueueStatus.DELIVERED, 0)
        delivered = counts.get(QueueStatus.DELIVERED, 0)
        failed = counts.get(QueueStatus.FAILED, 0) + counts.get(QueueStatus.EXHAUSTED, 0)
        pending = counts.get(QueueStatus.PENDING, 0) + counts.get(QueueStatus.PROCESSING, 0) + counts.get(QueueStatus.RETRYING, 0)
        return {"pending": pending, "sent": sent, "delivered": delivered, "failed": failed}

    async def list_bulk_message_jobs(self, *, skip: int, limit: int) -> tuple[list[BulkMessageJob], int]:
        total = await self._bulk_jobs.count({})
        items = await self._bulk_jobs.find_many({}, skip=skip, limit=limit, sort=[("created_at", -1)])
        return items, total

    async def cancel_bulk_message_job(self, job_id: str, actor: User) -> BulkMessageJob:
        job = await self.get_bulk_message_job(job_id)
        if job.status not in BulkMessageJobStatus.ACTIVE:
            raise ValidationError("Only a queued or processing job can be cancelled.")
        updated = await self._bulk_jobs.update(job_id, {"status": BulkMessageJobStatus.CANCELLED}, updated_by=actor.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.BULK_JOB_CANCELLED, user_id=actor.require_id(), metadata={"bulk_job_id": job_id})
        assert updated is not None
        return updated

    async def list_bulk_job_failed_messages(self, job_id: str) -> list[CommunicationQueueItem]:
        await self.get_bulk_message_job(job_id)
        return await self._queue.find_many(
            {"business_event": f"bulk:{job_id}", "status": {"$in": [QueueStatus.FAILED, QueueStatus.EXHAUSTED]}}, limit=1000
        )

    async def retry_bulk_job_failed(self, job_id: str, actor: User) -> int:
        failed_items = await self.list_bulk_job_failed_messages(job_id)
        for item in failed_items:
            await self.retry_message_now(item.require_id(), actor)
        return len(failed_items)

    async def _resolve_recipient_contact(self, recipient_type: str, recipient_id: str, channel: str) -> tuple[str | None, dict[str, str]]:
        """Returns `(recipient_address_or_None, variables)` — `None` means "skip, no
        contact method for this channel" (or the recipient no longer exists)."""
        if recipient_type == "lead":
            lead = await self._leads.find_by_id(recipient_id)
            if lead is None:
                return None, {}
            address = lead.mobile if channel in (Channel.WHATSAPP, Channel.SMS) else lead.email
            return address, {"customer_name": lead.full_name, "mobile": lead.mobile, "email": lead.email or ""}
        if recipient_type == "customer":
            customer = await self._customers.find_by_id(recipient_id)
            if customer is None:
                return None, {}
            address = customer.mobile if channel in (Channel.WHATSAPP, Channel.SMS) else customer.email
            return address, {"customer_name": customer.full_name, "mobile": customer.mobile, "email": customer.email or ""}
        return None, {}

    async def _enqueue_bulk_recipient(self, *, job: BulkMessageJob, recipient_id: str) -> str:
        """Returns `"queued"` | `"skipped_no_contact"` | `"skipped_duplicate"`. Idempotent
        — reuses the exact same `(business_event, entity_type, entity_id, channel)` dedup
        key `_enqueue` already established for the business-event poller, scoped to this
        job via a synthetic `business_event=f"bulk:{job_id}"`. A second processing pass
        over the same recipient (a worker restart resuming from a persisted `next_index`,
        or the same batch re-processed) never double-enqueues — this is the actual
        idempotency guarantee, not `next_index` itself (which is only a resume-from-here
        optimization, not a correctness requirement)."""
        job_id = job.require_id()
        existing = await self._queue.find_existing_for_event(
            business_event=f"bulk:{job_id}", entity_type=job.recipient_type, entity_id=recipient_id, channel=job.channel
        )
        if existing is not None:
            return "skipped_duplicate"

        recipient, variables = await self._resolve_recipient_contact(job.recipient_type, recipient_id, job.channel)
        if not recipient:
            return "skipped_no_contact"

        template = await self._templates.find_by_id(job.template_id)
        if template is None:
            return "skipped_no_contact"  # deleted mid-job — nothing to render/send

        rendered_body = template_engine.render(template.body, variables)
        rendered_subject = template_engine.render(template.subject, variables) if template.subject else None
        item = CommunicationQueueItem(
            channel=job.channel, recipient=recipient, template_id=job.template_id, variables=variables,
            rendered_subject=rendered_subject, rendered_body=rendered_body,
            business_event=f"bulk:{job_id}", entity_type=job.recipient_type, entity_id=recipient_id,
        )
        queue_item_id = await self._queue.insert(item)
        await write_audit_log(
            self._db, event_type=AuditEvent.MESSAGE_ENQUEUED, user_id=None,
            metadata={"queue_item_id": queue_item_id, "bulk_job_id": job_id, "channel": job.channel},
        )
        return "queued"

    async def process_bulk_message_jobs(self) -> None:
        """Worker-driven (Arq cron) — bulk sending is never done synchronously from the
        create-job request; only `CommunicationQueueItem` rows are inserted here (as
        `PENDING`), and the existing `process_pending_queue`/`process_retry_queue` cron
        jobs (unchanged) pick them up and actually talk to the provider, exactly like
        every other queued message. Resumable: progress (`next_index`) is persisted after
        every batch, so a worker restart mid-job simply resumes from the last completed
        batch — safe even if the same batch is re-processed, thanks to
        `_enqueue_bulk_recipient`'s own idempotency check."""
        jobs = await self._bulk_jobs.find_active(limit=20)
        for job in jobs:
            if job.status == BulkMessageJobStatus.QUEUED:
                await self._bulk_jobs.update(job.require_id(), {"status": BulkMessageJobStatus.PROCESSING})

            batch = job.recipient_ids[job.next_index : job.next_index + BULK_ENQUEUE_BATCH_SIZE]
            queued_delta = 0
            skipped_delta = 0
            for recipient_id in batch:
                outcome = await self._enqueue_bulk_recipient(job=job, recipient_id=recipient_id)
                if outcome == "queued":
                    queued_delta += 1
                elif outcome == "skipped_no_contact":
                    skipped_delta += 1
                # "skipped_duplicate" was already counted in queued_count the first time.

            next_index = job.next_index + len(batch)
            updates: dict[str, Any] = {
                "next_index": next_index, "queued_count": job.queued_count + queued_delta, "skipped_count": job.skipped_count + skipped_delta,
            }
            if next_index >= len(job.recipient_ids):
                updates["status"] = BulkMessageJobStatus.COMPLETED
            await self._bulk_jobs.update(job.require_id(), updates)
