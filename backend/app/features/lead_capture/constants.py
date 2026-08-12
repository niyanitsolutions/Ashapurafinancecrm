"""Module 9B — Lead Capture constants.

Scope: turning an inbound Website form submission, a Meta Lead Ads webhook
notification, or a staff-triggered manual import into a real Module 6A `Lead` — reusing
`LeadService.create_lead` unmodified (the exact reuse pattern Module 7 already
established for Referral Partner leads). A generic Webhook -> Provider -> Parser -> Lead
pipeline (`parsers.py`) is shared code; only the parsing of each source's own payload
shape is source-specific, mirroring 8's "generic executor + a few custom parsers" split
(decision 090) and 9A's "generic reachability check + a couple of real per-provider
checks" split (decision 094).
"""


class CaptureSourceKey:
    WEBSITE_FORM = "website_form"
    META_LEAD_ADS = "meta_lead_ads"
    MANUAL_API = "manual_api"

    ALL = (WEBSITE_FORM, META_LEAD_ADS, MANUAL_API)


class FailureReason:
    DUPLICATE = "duplicate"
    INVALID_DATA = "invalid_data"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    API_ERROR = "api_error"

    ALL = (DUPLICATE, INVALID_DATA, MISSING_REQUIRED_FIELDS, API_ERROR)


class FailureStatus:
    PENDING = "pending"  # awaiting first or next retry attempt (api_error only)
    RESOLVED = "resolved"  # a retry succeeded — resolved_lead_id is set
    EXHAUSTED = "exhausted"  # api_error hit escalation_max_retries with no success
    IGNORED = "ignored"  # duplicate/invalid_data/missing_required_fields — not retryable by nature

    ALL = (PENDING, RESOLVED, EXHAUSTED, IGNORED)


# Only a transient/technical failure is worth retrying automatically — duplicate/
# invalid-data/missing-fields are permanent until a human fixes the source data, not a
# transient condition that resolves itself.
RETRYABLE_REASONS = (FailureReason.API_ERROR,)

MAX_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_MINUTES = 15  # multiplied by 2^retry_count, same escalation-ladder shape as 6D's task escalation


class AuditEvent:
    LEAD_CAPTURED = "lead_captured"
    CAPTURE_FAILED = "capture_failed"
    CAPTURE_RETRIED = "capture_retried"
    SOURCE_REMAPPED = "capture_source_remapped"


# The one LeadActivity event type this module adds (Module 6A's `LeadActivity.event_type`
# is a free-form `^[a-z_]+$` field, not a closed enum — see docs/decisions/DECISIONS.md).
LEAD_ACTIVITY_CAPTURED = "captured"
