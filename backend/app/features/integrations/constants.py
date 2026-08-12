"""Module 9A — API Management constants.

Scope, per explicit instruction: this module only builds the integration *management*
platform — configuration storage, encryption, Enable/Disable, Test Connection. It never
sends a WhatsApp message, never fetches a Meta lead, never sends an SMS/email — those
remain 9B (Lead Capture)/9C (Communication)'s job, consuming what's configured here.

`system_settings.ApiSetting` (Module 4, frozen) already stores an encrypted config blob
per (provider, label) — this module is deliberately new/additive rather than an
extension of that frozen collection (decision — see docs/decisions/DECISIONS.md): it
adds concepts `ApiSetting` never had (an Active-per-type config, Test Connection with a
result history, Last Tested/Success/Failure tracking) that the freeze policy's "no
repurposing a collection for a new meaning" rule would otherwise block.
"""


class IntegrationType:
    META = "meta"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    MAPS = "maps"

    ALL = (META, WHATSAPP, SMS, EMAIL, MAPS)


class HealthStatus:
    """Reserved vocabulary only — `IntegrationConfig.health_status` (decision, given at
    Module 9A's freeze review) has no reader or writer anywhere yet. A future round
    could derive this from `last_success_at`/`last_failure_at` (e.g. recent failures ->
    WARNING, N consecutive failures -> ERROR)."""

    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"

    ALL = (HEALTHY, WARNING, ERROR)


class AuditEvent:
    PROVIDER_SEEDED = "integration_provider_seeded"  # unused at runtime — seed script only, listed for completeness
    CONFIG_CREATED = "integration_config_created"
    CONFIG_UPDATED = "integration_config_updated"
    CONFIG_ENABLED = "integration_config_enabled"
    CONFIG_DISABLED = "integration_config_disabled"
    CONFIG_ACTIVATED = "integration_config_activated"
    CONFIG_TESTED = "integration_config_tested"
    OAUTH_STARTED = "integration_oauth_started"
    OAUTH_CONNECTED = "integration_oauth_connected"
    OAUTH_DISCONNECTED = "integration_oauth_disconnected"
    TOKEN_REFRESHED = "integration_token_refreshed"
    TOKEN_REFRESH_FAILED = "integration_token_refresh_failed"


# A config key is treated as secret (encrypted at rest, masked in every API response —
# never returned in full) purely by naming convention — no per-provider field schema is
# maintained (matching decision 028's own "a single flexible blob avoids hardcoding a
# schema per provider" reasoning). Every literal secret field named in the brief across
# all 5 integration types (App Secret, Access Token, Webhook Verify Token, Webhook
# Secret, API Key, Password) contains one of these substrings.
SECRET_KEY_MARKERS = ("secret", "token", "key", "password")


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


# Meta OAuth Connect flow — scopes needed across the whole flow (Page list, Ad Account
# list, Lead Forms, Lead retrieval, and subscribing a Page's webhook). Requested once at
# the OAuth dialog rather than incrementally, since Graph API has no partial-consent retry.
META_OAUTH_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_metadata",
    "pages_manage_ads",
    "leads_retrieval",
    "ads_read",
    "business_management",
)

# Redis key prefixes for the CSRF-state/pending-selection handshake — short-lived, never
# persisted to Mongo (page/user tokens sit in Redis only until the Owner picks a Page and
# hits Connect, per the same "least persistence" instinct as SecureLinkRepository).
META_OAUTH_STATE_KEY_PREFIX = "meta_oauth_state:"
META_OAUTH_SESSION_KEY_PREFIX = "meta_oauth_session:"
META_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes to complete the Facebook login dialog
META_OAUTH_SESSION_TTL_SECONDS = 900  # 15 minutes to pick a Page/Ad Account/Forms and hit Connect

# A long-lived User Access Token lasts ~60 days — refresh once within this window of
# expiry so a Page's derived token never silently goes stale between Owner logins.
META_TOKEN_REFRESH_WINDOW_DAYS = 7
