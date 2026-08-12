"""Module 9A — API Management domain models.

`IntegrationConfig.config_encrypted` stores the entire provider config dict as one
`encrypt(json.dumps(...))` blob via Foundation's `security/encryption.py` — the exact
same primitive `system_settings.ApiSetting` already uses (decision 028), reused
unmodified, not duplicated. Per the user's own recommendation: a config is a *named*,
independently-credentialed instance ("Meta Production", "Meta Sandbox", ...), not one
row per integration type — `is_active` marks which single config is currently live for
its `integration_type` (enforced in service.py, not here).
"""

from datetime import datetime

from pydantic import Field

from app.features.integrations.constants import IntegrationType
from app.shared.base_document import BaseDocument


class IntegrationProvider(BaseDocument):
    """Seeded catalog — decision: which (integration_type, provider) pairs are known/
    offered today. Adding a new provider for an existing type (e.g. a second WhatsApp
    provider) is a new seeded row, not a code change to `IntegrationConfig`'s CRUD."""

    integration_type: str = Field(pattern=f"^({'|'.join(IntegrationType.ALL)})$")
    provider: str
    label: str


class IntegrationConfig(BaseDocument):
    integration_code: str  # AFS-INTG-000001
    integration_type: str = Field(pattern=f"^({'|'.join(IntegrationType.ALL)})$")
    provider: str  # ref: integration_providers, by (integration_type, provider)
    name: str  # "Meta Production", "WhatsApp Test", "SMTP Office365", ...

    config_encrypted: str

    is_enabled: bool = False
    # Only one config per `integration_type` may be True at a time (service-enforced) —
    # this is what 9B/9C would read to know which named config is actually live.
    is_active: bool = False

    last_tested_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_message: str | None = None

    # First-activation timestamp only — never overwritten by later re-activations, so it
    # reads as a genuine "Connected Since" rather than "most recently (re)activated at".
    activated_at: datetime | None = None

    # Meta-only signal: set when the webhook GET handshake (`verify_meta_challenge`)
    # succeeds — see lead_capture/service.py. Null for every other integration_type.
    webhook_verified_at: datetime | None = None

    # No longer purely reserved — see IntegrationsService._compute_health_status:
    # "error" (never tested successfully, or most recent test failed), "warning"
    # (tested good but webhook not yet verified or no lead received yet), "healthy"
    # (tested good + webhook verified + at least one lead received). Still same "reserve
    # a slot" posture as ReferralPartner.parent_partner_id (decision 080)/ScheduledReport
    # (decision 085) — just now with a real, additive computation, no schema change.
    health_status: str | None = None


class IntegrationTestLog(BaseDocument):
    """Append-only history of Test Connection attempts — `IntegrationConfig`'s own
    `last_tested_at`/etc. fields only ever show the *latest* attempt; this collection
    keeps every one, for an Integration Details page's test history."""

    config_id: str
    integration_type: str
    provider: str
    success: bool
    response_time_ms: int
    error_message: str | None = None
    tested_at: datetime
    graph_api_version: str | None = None  # Meta/Maps only — the hardcoded provider API version tested against
    tested_ip: str | None = None  # via the existing app.features.auth.dependencies.get_request_context
