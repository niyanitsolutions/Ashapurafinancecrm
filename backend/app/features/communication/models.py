"""Module 9C — Communication Engine domain models. Every send flows through
`CommunicationQueueItem` — no business module (Leads, Customer, Workflow Engine,
Reminders, Referral Partner Management, all frozen) is modified to call a provider
directly; a poller consumes their existing `audit_logs` entries instead (see
`constants.py`'s module docstring).
"""

from datetime import datetime

from pydantic import Field

from app.features.communication.constants import Channel, QueueStatus, TemplateCategory
from app.shared.base_document import BaseDocument


class CommunicationTemplate(BaseDocument):
    """Owner-authored — message content is never hardcoded into business logic. Ships
    with zero seeded rows (same posture as Module 4's Notification Templates, decision
    029 — real business copy is not invented here); the engine works, but nothing is
    actually sent for a given business event until the Owner creates a matching
    template. `status` (inherited) active/inactive lets one be retired without deleting
    it, same convention as ReminderRule/CommissionRule."""

    name: str
    channel: str = Field(pattern=f"^({'|'.join(Channel.ALL)})$")
    category: str = Field(pattern=f"^({'|'.join(TemplateCategory.ALL)})$")
    subject: str | None = None  # email only
    body: str
    variables: list[str] = Field(default_factory=list)  # variable names the body references, e.g. ["customer_name", "lead_code"]
    language: str = "en"  # future-ready — no other language is implemented, this is just the field


class CommunicationQueueItem(BaseDocument):
    channel: str = Field(pattern=f"^({'|'.join(Channel.ALL)})$")
    recipient: str  # a mobile number (whatsapp/sms) or email address
    template_id: str
    variables: dict[str, str] = Field(default_factory=dict)
    rendered_subject: str | None = None
    rendered_body: str

    status: str = Field(default=QueueStatus.PENDING, pattern=f"^({'|'.join(QueueStatus.ALL)})$")
    provider_config_id: str | None = None  # which Module 9A IntegrationConfig was used
    provider_message_id: str | None = None  # the provider's own tracking id, once sent
    retry_count: int = 0
    next_retry_at: datetime | None = None
    error_detail: str | None = None

    # Which business event triggered this (None for a future manual/API-driven send) —
    # never a new event type, always one of constants.py:BusinessEvent.
    business_event: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None

    sent_at: datetime | None = None
    delivered_at: datetime | None = None  # reserved — see docs/COMMUNICATION.md; no delivery-status webhook exists yet


class CommunicationHistory(BaseDocument):
    """One row per queue item's completed lifecycle — created once the item first
    reaches a terminal state and updated in place only by that same item's own later
    transitions (e.g. sent -> delivered, if a future delivery-status webhook is added).
    Never reused across different messages, and never deleted."""

    queue_item_id: str
    channel: str
    provider: str
    recipient: str
    template_id: str
    template_name: str
    variables: dict[str, str]
    status: str
    error: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    retry_count: int


class ProviderDeliveryLog(BaseDocument):
    """One row per actual attempt against a provider (distinct from
    `CommunicationHistory`, which is one row per queue item's final outcome) — lets
    "why did attempt 3 fail" stay answerable, the same append-only-attempt-log shape as
    9A's `IntegrationTestLog`/9B's retry-tracking on `CaptureFailure`."""

    queue_item_id: str
    channel: str
    provider: str
    attempt_number: int
    success: bool
    provider_message_id: str | None = None
    error: str | None = None
    response_time_ms: int | None = None
    attempted_at: datetime


class CommunicationCheckpoint(BaseDocument):
    """One row per polled business event (see `constants.py:BusinessEvent`), the same
    "don't rescan the whole append-only audit_logs collection every run" bookkeeping
    Module 6D's own `NotificationCheckpoint` established (decision 065) — a distinct
    collection rather than sharing 6D's, since sharing would mean modifying a frozen
    module's own collection semantics for an unrelated consumer."""

    business_event: str
    last_processed_at: datetime


class CommunicationPreference(BaseDocument):
    """Reserved, not implemented — decision, given at the user's own explicit
    instruction ("prepare for future support... do not implement UI yet, just reserve
    the model"). No code reads or writes this yet; the queue processor does not check
    it before sending. Same inert-reservation posture as `IntegrationConfig.
    health_status` (9A, decision 096) and `webhook_events` (9B, decision 103)."""

    user_id: str
    sms_enabled: bool = True
    whatsapp_enabled: bool = True
    email_enabled: bool = True
