from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder committed in every shipped env file (.env, .env.development, .env.staging,
# .env.production) — real deployments must override it. Checked at settings-load time
# (see `_reject_insecure_production_config` below) so a forgotten override fails startup
# instead of silently forging every access/refresh token with a known secret.
_PLACEHOLDER_JWT_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "AFS Financial CRM"
    api_v1_prefix: str = "/api/v1"

    # The single business timezone for the entire application — every business-day/
    # business-hour calculation (Geo Fencing, Dashboard "today", report date ranges,
    # reminders, ...) goes through `app/utils/datetime.py`'s IST helpers, which read
    # this value rather than hardcoding "Asia/Kolkata" a second time anywhere else.
    # Storage stays UTC regardless (see docs/TIMEZONE.md) — this only governs how
    # business dates/times are interpreted and displayed. A real IANA zone name
    # (`zoneinfo.ZoneInfo`), not a fixed offset, so it stays correct even if this ever
    # needs to change to a DST-observing zone in the future.
    timezone: str = "Asia/Kolkata"
    # Safe-by-default (same reasoning as `otp_mode` below): a deployment that forgets to
    # set DEBUG explicitly must not get Starlette's traceback-and-source-dump error page,
    # since FastAPI(debug=...) short-circuits the app's own safe 500 handler when True.
    debug: bool = False

    mongo_uri: str
    mongo_db_name: str

    redis_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Dedicated key for `app/security/encryption.py`'s at-rest field encryption (e.g.
    # integration credentials). Empty by default so local/staging keep working exactly
    # as before (falls back to deriving from `jwt_secret_key`, unchanged from prior
    # behavior); production must set a real one — see the validator below. Deliberately
    # separate from `jwt_secret_key` so rotating one doesn't make the other's encrypted
    # data unreadable.
    encryption_key: str = ""

    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5
    max_login_attempts: int = 5
    account_lock_minutes: int = 15
    secure_link_expire_minutes: int = 60
    otp_verified_token_expire_minutes: int = 10

    # The single flag governing every OTP dev-mode behavior (see otp_service.issue_otp
    # and AuthService._deliver_otp): "development" uses a fixed, well-known OTP and logs
    # it to the console instead of sending SMS; "production" generates a real random OTP
    # and attempts real SMS delivery. Storage, hashing, expiry, attempt-limiting, and
    # verification (otp_service.verify_stored_otp) are byte-for-byte identical either
    # way — nothing about the OTP *architecture* changes, only where the value comes
    # from and how it's delivered. Defaults to "production" (safe-by-default: a
    # deployment that forgets to set this never silently accepts a fixed OTP);
    # local dev overrides it via .env/.env.local.
    otp_mode: str = Field(default="production", pattern=r"^(development|production)$")

    # TEMPORARY — MSG91 DLT Sender ID/template approval testing bypass for customer
    # SELF-REGISTRATION ONLY (see CustomerService.bypass_verify_registration_mobile). The
    # single flag is deliberately the *only* gate — no allowlist — since it's an explicit,
    # administrator-controlled production env var, not something a caller can influence.
    # Must be set back to false once DLT approval lands, and the whole feature removed
    # once real MSG91 OTP delivery is verified end-to-end. Never consulted by login,
    # forgot-password, or any other OTP purpose — those keep using the real Redis OTP
    # flow regardless of this value. Off by default.
    registration_otp_bypass: bool = False

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = ""

    cors_origins: str = "http://localhost:5173"

    # Where the Meta OAuth callback redirects the browser back to after Facebook login
    # (see integrations/router.py's public oauth/callback route) — the SPA has no server
    # page to render its own redirect target, so this is a plain origin, not a full URL.
    frontend_base_url: str = "http://localhost:5173"

    rate_limit_per_minute: int = 60

    # Hosts allowed to set X-Forwarded-For/X-Forwarded-Proto and have them trusted (see
    # ProxyHeadersMiddleware in main.py). Must be the reverse proxy's own address(es) —
    # e.g. "127.0.0.1" for Nginx on the same EC2 instance in front of Uvicorn — never
    # "*", or any client could forge their own IP and dodge both rate limiting
    # (rate_limit.py keys on this) and the IP recorded in sessions/audit logs.
    trusted_proxy_ips: str = "127.0.0.1"

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _reject_insecure_production_config(self) -> "Settings":
        """Local/staging convenience must never reach `app_env=production` unnoticed —
        the committed `.env.production` placeholder (`JWT_SECRET_KEY=change-me`) would
        otherwise let anyone who has read the repository forge tokens for every role.
        Only gated on `production` so `.env.local`/`.env.development` keep working
        exactly as before."""
        if self.app_env != "production":
            return self
        if self.jwt_secret_key == _PLACEHOLDER_JWT_SECRET or len(self.jwt_secret_key) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be a real, high-entropy secret (>= 32 characters) in production — "
                "refusing to start with the placeholder or a short value."
            )
        if self.debug:
            raise ValueError("DEBUG must be false in production — it disables the app's safe error handler.")
        if not self.encryption_key or len(self.encryption_key) < 32:
            raise ValueError(
                "ENCRYPTION_KEY must be a real, high-entropy secret (>= 32 characters) in production — "
                "refusing to start by deriving it from JWT_SECRET_KEY instead."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
