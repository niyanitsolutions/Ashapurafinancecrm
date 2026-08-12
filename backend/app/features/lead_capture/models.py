"""Module 9B — Lead Capture domain models. `Lead` (Module 6A, frozen) is never modified
— every successful capture creates an ordinary `Lead` via the frozen, unmodified
`LeadService.create_lead`, exactly like Module 7 did for Referral Partner leads.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.features.lead_capture.constants import CaptureSourceKey, FailureReason, FailureStatus
from app.shared.base_document import BaseDocument


class CaptureSource(BaseDocument):
    """Seeded catalog — Source Mapping (never hardcoded): which `lead_sources` (Module 4)
    row a capture channel attributes its leads to. Owner-remappable via
    `PATCH /lead-capture/sources/{key}` without any code change. `default_product_category`/
    `default_product_id` are optional — Meta Lead Ads forms don't naturally carry product
    info, so a capture whose payload doesn't supply one falls back to these if set, or is
    logged as a `missing_required_fields` capture failure if neither is available."""

    key: str = Field(pattern=f"^({'|'.join(CaptureSourceKey.ALL)})$")
    label: str
    lead_source_id: str  # ref: system_settings.lead_sources
    default_product_category: str | None = None
    default_product_id: str | None = None


class CaptureFailure(BaseDocument):
    """Every inbound request that didn't become a Lead — never silently dropped. Only
    `failure_reason=api_error` is retried automatically (a transient/technical
    condition); duplicate/invalid_data/missing_required_fields need a human to fix the
    source data, so they're logged for visibility, not retried."""

    capture_source: str = Field(pattern=f"^({'|'.join(CaptureSourceKey.ALL)})$")
    failure_reason: str = Field(pattern=f"^({'|'.join(FailureReason.ALL)})$")
    raw_payload: dict[str, Any]
    error_detail: str | None = None

    status: str = Field(default=FailureStatus.PENDING, pattern=f"^({'|'.join(FailureStatus.ALL)})$")
    retry_count: int = 0
    next_retry_at: datetime | None = None
    resolved_lead_id: str | None = None


class CaptureReceipt(BaseDocument):
    """Idempotency record — prevents creating a second Lead from the same external
    notification (e.g. a retried Meta webhook delivery for the same `leadgen_id`).
    Website form submissions have no natural external id and don't use this; 6A's own
    `duplicate_of_lead_ids` cross-lead flagging (decision 041) still applies regardless,
    unaffected by this idempotency check, which only prevents literal re-processing of
    the exact same inbound notification."""

    capture_source: str
    external_id: str  # e.g. Meta's leadgen_id — unique per (capture_source, external_id)
    lead_id: str


class WebhookEvent(BaseDocument):
    """Reserved for future observability — decision, given at Module 9B's freeze
    review. No code writes or reads this collection yet; `capture_failures` already
    records failed attempts, but this would record *every* inbound webhook event
    (received/validated/parsed/lead_created/completed, or received/failed/retried/
    completed) — useful later for answering "how many webhook calls did we get today,"
    including the ones that succeeded, which `capture_failures` alone can't show."""

    capture_source: str
    external_id: str | None = None
    stage: str  # received / validated / parsed / lead_created / completed / failed / retried
    detail: dict[str, Any] | None = None
