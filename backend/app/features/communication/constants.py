"""Module 9C — Communication Engine constants.

Scope, per explicit instruction: a centralized send engine only — not a second
notification system (Module 6D already owns internal/in-app notifications) and not an
integration system (Module 9A already owns provider credentials/config). Business
modules never call a provider directly; everything flows through
`Business Module -> Communication Service -> Queue -> Provider Adapter -> Provider ->
Delivery Status -> Communication History`.

Triggering reuses the exact "poll `audit_logs` for events a frozen module already
writes" pattern Module 6D established (decision 065) and Module 7/9B reused since — no
frozen module (Leads, Customer, Workflow Engine, Reminders, Referral Partner
Management) is modified to call this engine directly; a small, fixed set of *existing*
audit event types is consumed instead. OTP is a template category reserved for future
use only — see docs/COMMUNICATION.md for why OTP delivery itself isn't wired through
this engine this round (Auth, Module 1, is frozen and OTP delivery must stay synchronous).
"""


class Channel:
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"

    ALL = (WHATSAPP, SMS, EMAIL)


class TemplateCategory:
    """Open examples named in the brief — not a schema restriction on message *content*
    (that stays entirely Owner-authored, per "don't hardcode message content"), just the
    catalog of category values a template/business-event pairing can use."""

    OTP = "otp"
    WELCOME = "welcome"
    LEAD_ASSIGNED = "lead_assigned"
    REMINDER = "reminder"
    APPLICATION_SUBMITTED = "application_submitted"
    DOCUMENT_REQUEST = "document_request"
    COMMISSION_APPROVED = "commission_approved"
    # Added for the Secure Application Link redesign (Module 6B) — sent synchronously
    # via CommunicationService.send_now, not the business-event poller (there is no
    # BusinessEvent/audit-log entry for this one; see send_now's own docstring).
    SECURE_LINK = "secure_link"

    ALL = (OTP, WELCOME, LEAD_ASSIGNED, REMINDER, APPLICATION_SUBMITTED, DOCUMENT_REQUEST, COMMISSION_APPROVED, SECURE_LINK)


class QueueStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"  # reserved — see docs/COMMUNICATION.md; no code sets this yet (no delivery-status webhook exists)
    FAILED = "failed"
    RETRYING = "retrying"
    EXHAUSTED = "exhausted"

    ALL = (PENDING, PROCESSING, SENT, DELIVERED, FAILED, RETRYING, EXHAUSTED)
    TERMINAL = (SENT, DELIVERED, FAILED, EXHAUSTED)


MAX_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_MINUTES = 5  # multiplied by 2^attempt — same escalation shape as 6D/9B's own retry ladders


class BusinessEvent:
    """The fixed set of *existing* business events this engine consumes — never a new
    event a frozen module has to be modified to emit. Each maps 1:1 to an
    already-written `audit_logs` event_type (see POLLED_AUDIT_EVENT_TYPES) and a
    `CommunicationTemplate.category` an Owner can author a template against."""

    LEAD_ASSIGNED = "lead_assigned"
    REMINDER_TRIGGERED = "reminder_triggered"
    APPLICATION_SUBMITTED = "application_submitted"
    DOCUMENT_REQUESTED = "document_requested"
    COMMISSION_READY = "commission_ready"

    ALL = (LEAD_ASSIGNED, REMINDER_TRIGGERED, APPLICATION_SUBMITTED, DOCUMENT_REQUESTED, COMMISSION_READY)


# BusinessEvent -> the CommunicationTemplate.category an Owner authors a template
# under, and the literal audit_logs event_type this poller scans for.
TEMPLATE_CATEGORY_BY_EVENT: dict[str, str] = {
    BusinessEvent.LEAD_ASSIGNED: TemplateCategory.LEAD_ASSIGNED,
    BusinessEvent.REMINDER_TRIGGERED: TemplateCategory.REMINDER,
    BusinessEvent.APPLICATION_SUBMITTED: TemplateCategory.APPLICATION_SUBMITTED,
    BusinessEvent.DOCUMENT_REQUESTED: TemplateCategory.DOCUMENT_REQUEST,
    BusinessEvent.COMMISSION_READY: TemplateCategory.COMMISSION_APPROVED,
}

AUDIT_EVENT_TYPE_BY_BUSINESS_EVENT: dict[str, str] = {
    BusinessEvent.LEAD_ASSIGNED: "lead_assigned",
    BusinessEvent.REMINDER_TRIGGERED: "notification_created",  # filtered further by metadata.notification_type == "reminder_triggered"
    BusinessEvent.APPLICATION_SUBMITTED: "application_submitted",
    BusinessEvent.DOCUMENT_REQUESTED: "workflow_documents_requested",
    BusinessEvent.COMMISSION_READY: "commission_entry_created",
}

POLLED_AUDIT_EVENT_TYPES = tuple(set(AUDIT_EVENT_TYPE_BY_BUSINESS_EVENT.values()))


class AuditEvent:
    TEMPLATE_CREATED = "communication_template_created"
    TEMPLATE_UPDATED = "communication_template_updated"
    MESSAGE_ENQUEUED = "communication_message_enqueued"
    MESSAGE_SENT = "communication_message_sent"
    MESSAGE_FAILED = "communication_message_failed"
    MESSAGE_RETRIED = "communication_message_retried"
    MESSAGE_DELIVERED = "communication_message_delivered"  # Stage 2 — set only by a real provider DLR webhook (MSG91), never inferred from a successful send
    WEBHOOK_REJECTED = "communication_webhook_rejected"  # invalid/missing secret, or malformed payload
    BULK_JOB_CREATED = "communication_bulk_job_created"  # Stage 3
    BULK_JOB_CANCELLED = "communication_bulk_job_cancelled"  # Stage 3


class BulkMessageJobStatus:
    """Stage 3 — Bulk Messaging. `queued`/`processing` are both picked up by the worker
    cron (`process_bulk_message_jobs`); the distinction is purely a display nicety
    (has this job's very first batch started yet). No `failed` job-level status exists —
    a job always reaches `completed` once every recipient has been enqueued-or-skipped;
    per-recipient send failures live on the individual `CommunicationQueueItem`s, exactly
    like every other queued message, not on the job itself."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    ALL = (QUEUED, PROCESSING, COMPLETED, CANCELLED)
    ACTIVE = (QUEUED, PROCESSING)


# How many recipients the resumable bulk-enqueue worker task processes per job per tick
# — bounds a single Arq job run's duration and keeps a worker restart's replay window
# small, matching the same "batching" instinct MAX_RETRY_ATTEMPTS/RETRY_BACKOFF_MINUTES
# already established for the retry queue.
BULK_ENQUEUE_BATCH_SIZE = 100
