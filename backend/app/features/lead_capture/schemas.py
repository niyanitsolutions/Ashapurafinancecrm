from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class WebsiteCaptureRequest(BaseModel):
    """Deliberately lenient (all-optional except a bare presence check happens in the
    service, not here) — a malformed submission must become a `CaptureFailure` row,
    never just a bare HTTP 422 with no record (per explicit instruction: "never lose
    inbound requests"). Strict Pydantic-level validation would reject before the
    service ever got a chance to log it."""

    full_name: str | None = None
    mobile: str | None = None
    email: str | None = None
    product_category: str | None = None
    product_id: str | None = None
    remarks: str | None = None
    form_id: str | None = None
    # Reserved per the user's own recommendation — captured into the Lead's own
    # Timeline metadata when the calling website supplies them, never fabricated when
    # absent (see parsers.py:extract_source_metadata).
    form_version: str | None = None
    utm_source: str | None = None
    utm_campaign: str | None = None
    utm_medium: str | None = None


class WebsiteCaptureResponse(BaseModel):
    status: str  # "created"
    lead_code: str


class ManualCaptureRequest(BaseModel):
    """Authenticated, controlled (Owner/Employee) — unlike Website/Meta, strict
    validation here is fine: the caller can just fix their request and resubmit, so
    there's no need for a `CaptureFailure` row on a bad request."""

    full_name: str
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    email: EmailStr | None = None
    product_category: str
    product_id: str
    remarks: str | None = None


class CaptureSourceResponse(BaseModel):
    id: str
    key: str
    label: str
    lead_source_id: str
    default_product_category: str | None
    default_product_id: str | None


class UpdateCaptureSourceRequest(BaseModel):
    lead_source_id: str | None = None
    default_product_category: str | None = None
    default_product_id: str | None = None


class CaptureFailureResponse(BaseModel):
    id: str
    capture_source: str
    failure_reason: str
    raw_payload: dict[str, Any]
    error_detail: str | None
    status: str
    retry_count: int
    next_retry_at: datetime | None
    resolved_lead_id: str | None
    created_at: datetime
