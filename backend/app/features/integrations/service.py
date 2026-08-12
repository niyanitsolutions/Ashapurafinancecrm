"""Module 9A — API Management business logic.

Encryption is Foundation's own `security/encryption.py`, unmodified — the same
primitive `system_settings.ApiSetting` already uses (decision 028). No business action
(sending WhatsApp/SMS/email, fetching a Meta lead) is ever triggered from here — that's
9B/9C's job, consuming what's configured here.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.core.exceptions import NotFoundError, ValidationError
from app.features.auth.models import User
from app.features.integrations import mappers
from app.features.integrations import meta_status as meta_status_client
from app.features.integrations import oauth as oauth_client
from app.features.integrations import testers as testers_module
from app.features.integrations.constants import (
    META_OAUTH_SESSION_KEY_PREFIX,
    META_OAUTH_SESSION_TTL_SECONDS,
    META_OAUTH_STATE_KEY_PREFIX,
    META_OAUTH_STATE_TTL_SECONDS,
    META_TOKEN_REFRESH_WINDOW_DAYS,
    AuditEvent,
    HealthStatus,
    IntegrationType,
    is_secret_key,
)
from app.features.integrations.models import (
    IntegrationConfig,
    IntegrationProvider,
    IntegrationTestLog,
)
from app.features.integrations.repository import (
    IntegrationConfigRepository,
    IntegrationProviderRepository,
    IntegrationTestLogRepository,
)
from app.features.integrations.schemas import (
    CreateIntegrationConfigRequest,
    MetaStatusResponse,
    MissingPermissionResponse,
    OAuthAdAccountOption,
    OAuthConnectRequest,
    OAuthFormOption,
    OAuthPageOption,
    OAuthSessionResponse,
    SetupProgressResponse,
    TestConnectionResponse,
    TestDraftConnectionRequest,
    UpdateIntegrationConfigRequest,
)
from app.features.integrations.testers import GRAPH_API_VERSION, REQUIRED_META_PERMISSIONS, TESTERS
from app.features.lead_capture.constants import CaptureSourceKey
from app.features.lead_capture.repository import CaptureReceiptRepository
from app.security.encryption import decrypt, encrypt
from app.shared.audit_log import write_audit_log
from app.utils.datetime import ensure_utc, utc_now
from app.utils.id_generator import IdPrefix, generate_id


class IntegrationsService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._redis = redis
        self._providers = IntegrationProviderRepository(db)
        self._configs = IntegrationConfigRepository(db)
        self._test_logs = IntegrationTestLogRepository(db)
        # Read-only reuse of Module 9B's own collection — same "compose across features from
        # whichever feature owns the outward-facing API" pattern used throughout this project
        # (e.g. Module 6C's lazy case sync reading Module 6B's Applications, decision 058).
        self._capture_receipts = CaptureReceiptRepository(db)

    # ================================================================== providers (seeded catalog, read-only)

    async def list_providers(self) -> list[IntegrationProvider]:
        return await self._providers.list_all()

    # ================================================================== configs

    async def create_config(self, payload: CreateIntegrationConfigRequest, actor: User) -> tuple[IntegrationConfig, dict[str, str]]:
        provider = await self._providers.find_by_type_and_provider(payload.integration_type, payload.provider)
        if provider is None:
            raise ValidationError(f"Unknown provider '{payload.provider}' for integration type '{payload.integration_type}'.")

        config_values = dict(payload.config)
        generated: dict[str, str] = {}
        if payload.integration_type == IntegrationType.META:
            # No reason to make an Owner hand-type random tokens — generated once here and
            # handed back in plaintext on this response only (see router.create_config),
            # then stored/read exactly like any other config value everywhere else
            # (verify_meta_challenge/verify_signature in lead_capture never know the
            # difference between a generated value and a manually-entered one).
            for key in ("webhook_verify_token", "webhook_secret"):
                if not config_values.get(key):
                    generated[key] = config_values[key] = secrets.token_urlsafe(32)

        integration_code = await generate_id(self._db, IdPrefix.INTEGRATION)
        config = IntegrationConfig(
            integration_code=integration_code, integration_type=payload.integration_type, provider=payload.provider, name=payload.name,
            config_encrypted=encrypt(json.dumps(config_values)), created_by=actor.require_id(),
        )
        config_id = await self._configs.insert(config)
        await write_audit_log(self._db, event_type=AuditEvent.CONFIG_CREATED, user_id=actor.require_id(), metadata={"config_id": config_id})
        found = await self._configs.find_by_id(config_id)
        assert found is not None
        return found, generated

    async def list_configs(self, *, integration_type: str | None, skip: int, limit: int, sort: list[tuple[str, int]] | None) -> tuple[list[IntegrationConfig], int]:
        return await self._configs.search_and_filter(integration_type=integration_type, skip=skip, limit=limit, sort=sort)

    async def get_config(self, config_id: str) -> IntegrationConfig:
        config = await self._configs.find_by_id(config_id)
        if config is None:
            raise NotFoundError("Integration config not found.")
        return config

    async def update_config(self, config_id: str, payload: UpdateIntegrationConfigRequest, actor: User) -> IntegrationConfig:
        config = await self.get_config(config_id)
        updates: dict[str, Any] = {}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.config is not None:
            current = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
            # A client that re-submits the form without touching a masked secret field
            # echoes back exactly what config_to_response sent it — mask_secret(current
            # value) — which must be treated as "leave unchanged," not encrypted over
            # the real secret. Only skips a field whose submitted value IS that exact
            # mask of the CURRENTLY stored value, so a genuine new secret that happens
            # to start with an asterisk is never silently dropped.
            incoming = {
                k: v for k, v in payload.config.items()
                if not (is_secret_key(k) and k in current and v == mappers.mask_secret(str(current[k])))
            }
            credentials_changed = any(current.get(k) != v for k, v in incoming.items())
            current.update(incoming)
            updates["config_encrypted"] = encrypt(json.dumps(current))
            if credentials_changed:
                # Editing credentials must require re-proving them — a stale "last success"
                # from the *previous* credentials must never keep implying "still connected."
                updates["last_success_at"] = None
                updates["is_active"] = False
                updates["health_status"] = None

        updated = await self._configs.update(config_id, updates, updated_by=actor.require_id()) if updates else config
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.CONFIG_UPDATED, user_id=actor.require_id(), metadata={"config_id": config_id})
        return updated

    async def set_enabled(self, config_id: str, *, enabled: bool, actor: User) -> IntegrationConfig:
        await self.get_config(config_id)
        updates: dict[str, Any] = {"is_enabled": enabled}
        if not enabled:
            updates["is_active"] = False  # an active config must be enabled — disabling one clears active too
        updated = await self._configs.update(config_id, updates, updated_by=actor.require_id())
        assert updated is not None
        event = AuditEvent.CONFIG_ENABLED if enabled else AuditEvent.CONFIG_DISABLED
        await write_audit_log(self._db, event_type=event, user_id=actor.require_id(), metadata={"config_id": config_id})
        return updated

    async def activate_config(self, config_id: str, actor: User) -> IntegrationConfig:
        config = await self.get_config(config_id)
        if not config.is_enabled:
            raise ValidationError("Only an enabled configuration can be made active. Enable it first.")
        if config.last_success_at is None:
            raise ValidationError("Test the connection successfully before activating.")
        await self._configs.deactivate_others(config.integration_type, exclude_id=config_id)
        updates: dict[str, Any] = {"is_active": True}
        if config.activated_at is None:
            updates["activated_at"] = utc_now()  # first activation only — never overwritten later
        updated = await self._configs.update(config_id, updates, updated_by=actor.require_id())
        assert updated is not None
        await write_audit_log(self._db, event_type=AuditEvent.CONFIG_ACTIVATED, user_id=actor.require_id(), metadata={"config_id": config_id})
        return updated

    async def test_connection(self, config_id: str, actor: User, *, ip_address: str | None = None) -> TestConnectionResponse:
        config = await self.get_config(config_id)
        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}

        tester = TESTERS[config.integration_type]
        outcome = await tester(decrypted)
        tested_at = utc_now()

        updates: dict[str, Any] = {"last_tested_at": tested_at}
        tentative_success_at = config.last_success_at
        tentative_failure_at = config.last_failure_at
        if outcome.success:
            updates["last_success_at"] = tentative_success_at = tested_at
            updates["last_error_message"] = None
        else:
            updates["last_failure_at"] = tentative_failure_at = tested_at
            updates["last_error_message"] = outcome.error_message
        updates["health_status"] = await self._compute_health_status(
            integration_type=config.integration_type, last_success_at=tentative_success_at,
            last_failure_at=tentative_failure_at, webhook_verified_at=config.webhook_verified_at,
        )
        await self._configs.update(config_id, updates, updated_by=actor.require_id())

        graph_api_version = GRAPH_API_VERSION if config.integration_type in (IntegrationType.META, IntegrationType.MAPS) else None
        log = IntegrationTestLog(
            config_id=config_id, integration_type=config.integration_type, provider=config.provider, success=outcome.success,
            response_time_ms=outcome.response_time_ms, error_message=outcome.error_message, tested_at=tested_at,
            graph_api_version=graph_api_version, tested_ip=ip_address, created_by=actor.require_id(),
        )
        await self._test_logs.insert(log)
        await write_audit_log(
            self._db, event_type=AuditEvent.CONFIG_TESTED, user_id=actor.require_id(), metadata={"config_id": config_id, "success": outcome.success}
        )
        return mappers.test_result_to_response(outcome, tested_at)

    async def test_draft_connection(self, payload: TestDraftConnectionRequest) -> TestConnectionResponse:
        """Same tester dispatch as the real `/test` endpoint, but against raw credentials
        before any `IntegrationConfig` row exists — nothing is persisted (no config, no
        IntegrationTestLog, no audit log): lets an Owner prove credentials work before
        committing to Save, matching the testers' own "never a business action" principle."""
        tester = TESTERS.get(payload.integration_type)
        if tester is None:
            raise ValidationError(f"Unknown integration_type '{payload.integration_type}'.")
        outcome = await tester(payload.config)
        return mappers.test_result_to_response(outcome, utc_now())

    async def list_test_logs(self, config_id: str) -> list[IntegrationTestLog]:
        await self.get_config(config_id)
        return await self._test_logs.find_for_config(config_id)

    # ================================================================== connection health / status

    async def _compute_health_status(
        self, *, integration_type: str, last_success_at: datetime | None, last_failure_at: datetime | None, webhook_verified_at: datetime | None,
    ) -> str | None:
        # Mongo/Motor round-trips a stored datetime as naive even though every write here
        # uses tz-aware `utc_now()` (see app.utils.datetime.ensure_utc) — normalize both
        # before comparing, since one side may be a freshly-computed aware value (this same
        # call, `tested_at`) and the other read back from the database as naive.
        last_success_at = ensure_utc(last_success_at) if last_success_at else None
        last_failure_at = ensure_utc(last_failure_at) if last_failure_at else None
        if last_success_at is None:
            return HealthStatus.ERROR if last_failure_at is not None else None
        if last_failure_at is not None and last_failure_at > last_success_at:
            return HealthStatus.ERROR
        if integration_type != IntegrationType.META:
            return HealthStatus.HEALTHY
        if webhook_verified_at is None:
            return HealthStatus.WARNING
        total = await self._capture_receipts.count_for_source(CaptureSourceKey.META_LEAD_ADS)
        return HealthStatus.HEALTHY if total > 0 else HealthStatus.WARNING

    async def get_meta_status(self, config_id: str) -> MetaStatusResponse:
        config = await self.get_config(config_id)
        total_leads_imported = await self._capture_receipts.count_for_source(CaptureSourceKey.META_LEAD_ADS)

        if config.integration_type != IntegrationType.META:
            return MetaStatusResponse(
                health_status=config.health_status,
                setup_progress=SetupProgressResponse(
                    credentials_entered=False, test_connection_passed=config.last_success_at is not None,
                    saved=True, activated=config.is_active, webhook_verified=False, first_lead_received=False,
                ),
                completed_steps=0, total_steps=6, ad_accounts_count=None, pages_count=None, lead_forms_count=None,
                webhook_verified_at=None, last_lead_received_at=None, total_leads_imported=0, connected_since=config.activated_at,
                missing_permissions=[], token_expires_at=None, belongs_to_app_name=None, graph_api_version=GRAPH_API_VERSION,
            )

        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        access_token, app_id, app_secret = decrypted.get("access_token"), decrypted.get("app_id"), decrypted.get("app_secret")
        # ROOT-CAUSE FIX: /me/accounts and /me/adaccounts list what a *User* manages —
        # they require the long-lived User Access Token, never a Page Access Token.
        # `access_token` here is always the Page token (set in
        # IntegrationsService.connect_meta_oauth); `user_access_token` is the User token
        # saved alongside it under its own key. A config that was never connected via
        # OAuth (no `user_access_token` at all) simply can't show these two counts —
        # same "could not be determined" behavior this code already had for a missing
        # `access_token`, not a new failure mode.
        user_access_token = decrypted.get("user_access_token")

        ad_accounts_count: int | None = None
        pages: list[dict[str, str]] | None = None
        lead_forms_count: int | None = None
        token_expires_at: datetime | None = None
        belongs_to_app_name: str | None = None
        missing_permissions: list[MissingPermissionResponse] = []

        if access_token:
            if user_access_token:
                ad_accounts_count = await meta_status_client.fetch_ad_accounts_count(user_access_token)
                pages = await meta_status_client.fetch_pages(user_access_token)
                if pages is not None:
                    # {page_id}/leadgen_forms is Page-scoped — correctly keeps using the
                    # Page Access Token, unchanged.
                    lead_forms_count = await meta_status_client.fetch_lead_forms_count(access_token, [p["id"] for p in pages])
            if app_id and app_secret:
                data, _error = await testers_module.fetch_debug_token(access_token, app_id, app_secret)
                if data:
                    expires_at_ts = data.get("expires_at")
                    token_expires_at = datetime.fromtimestamp(expires_at_ts, tz=UTC) if expires_at_ts else None
                    belongs_to_app_name = data.get("application")
                    scopes = set(data.get("scopes") or [])
                    missing_permissions = [
                        MissingPermissionResponse(permission=p, why_needed=why) for p, why in REQUIRED_META_PERMISSIONS.items() if p not in scopes
                    ]

        latest_receipt = await self._capture_receipts.find_latest_for_source(CaptureSourceKey.META_LEAD_ADS)
        health_status = await self._compute_health_status(
            integration_type=config.integration_type, last_success_at=config.last_success_at,
            last_failure_at=config.last_failure_at, webhook_verified_at=config.webhook_verified_at,
        )

        setup_progress = SetupProgressResponse(
            credentials_entered=bool(decrypted),
            test_connection_passed=config.last_success_at is not None,
            saved=True,
            activated=config.is_active,
            webhook_verified=config.webhook_verified_at is not None,
            first_lead_received=total_leads_imported > 0,
        )
        completed_steps = sum(
            (
                setup_progress.credentials_entered, setup_progress.test_connection_passed, setup_progress.saved,
                setup_progress.activated, setup_progress.webhook_verified, setup_progress.first_lead_received,
            )
        )

        user_token_expires_at_raw = decrypted.get("user_token_expires_at")
        user_token_expires_at = ensure_utc(datetime.fromisoformat(user_token_expires_at_raw)) if user_token_expires_at_raw else None
        last_refresh_doc = await self._db["audit_logs"].find_one(
            {"event_type": AuditEvent.TOKEN_REFRESHED, "metadata.config_id": config.require_id()}, sort=[("created_at", -1)]
        )
        selected_forms_raw = decrypted.get("selected_forms", "")
        connected_form_count = len([f for f in selected_forms_raw.split(",") if f]) or None

        return MetaStatusResponse(
            health_status=health_status, setup_progress=setup_progress, completed_steps=completed_steps, total_steps=6,
            ad_accounts_count=ad_accounts_count, pages_count=len(pages) if pages is not None else None, lead_forms_count=lead_forms_count,
            webhook_verified_at=config.webhook_verified_at, last_lead_received_at=latest_receipt.created_at if latest_receipt else None,
            total_leads_imported=total_leads_imported, connected_since=config.activated_at, missing_permissions=missing_permissions,
            token_expires_at=token_expires_at, belongs_to_app_name=belongs_to_app_name, graph_api_version=GRAPH_API_VERSION,
            user_token_expires_at=user_token_expires_at, last_token_refresh_at=ensure_utc(last_refresh_doc["created_at"]) if last_refresh_doc else None,
            connected_page_name=decrypted.get("page_name") or None, connected_ad_account_id=decrypted.get("ad_account_id") or None,
            connected_form_count=connected_form_count,
        )

    # ================================================================== Meta OAuth Connect flow

    async def _require_meta_config(self, config_id: str) -> IntegrationConfig:
        config = await self.get_config(config_id)
        if config.integration_type != IntegrationType.META:
            raise ValidationError("OAuth Connect is only available for Meta configurations.")
        return config

    async def start_meta_oauth(self, config_id: str, actor: User, *, redirect_uri: str) -> str:
        config = await self._require_meta_config(config_id)
        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        app_id = decrypted.get("app_id")
        if not app_id:
            raise ValidationError("Set an App ID before connecting to Facebook.")

        nonce = uuid4().hex
        await self._redis.set(f"{META_OAUTH_STATE_KEY_PREFIX}{nonce}", config_id, ex=META_OAUTH_STATE_TTL_SECONDS)
        state = encrypt(json.dumps({"config_id": config_id, "nonce": nonce}))
        await write_audit_log(self._db, event_type=AuditEvent.OAUTH_STARTED, user_id=actor.require_id(), metadata={"config_id": config_id})
        return oauth_client.build_authorize_url(app_id=app_id, redirect_uri=redirect_uri, state=state)

    async def handle_meta_oauth_callback(self, *, code: str, state: str, redirect_uri: str) -> str:
        """Verifies the CSRF state, completes the code -> long-lived user token exchange,
        fetches the Pages/Ad Accounts the token can see, and stashes that (including Page
        tokens) in a short-lived Redis session — nothing touches Mongo until Connect.
        Returns the new session_id for the router to redirect the browser back with."""
        try:
            decoded = json.loads(decrypt(state))
            config_id, nonce = str(decoded["config_id"]), str(decoded["nonce"])
        except Exception as exc:
            raise ValidationError("Invalid or expired OAuth state.") from exc

        state_key = f"{META_OAUTH_STATE_KEY_PREFIX}{nonce}"
        stored_config_id = await self._redis.get(state_key)
        if stored_config_id != config_id:
            raise ValidationError("Invalid or expired OAuth state.")
        await self._redis.delete(state_key)

        config = await self._require_meta_config(config_id)
        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        app_id, app_secret = decrypted.get("app_id"), decrypted.get("app_secret")
        if not app_id or not app_secret:
            raise ValidationError("App ID and App Secret must be set before connecting to Facebook.")

        short_lived_token, _ = await oauth_client.exchange_code_for_token(app_id=app_id, app_secret=app_secret, redirect_uri=redirect_uri, code=code)
        user_access_token, expires_in = await oauth_client.exchange_for_long_lived_token(app_id=app_id, app_secret=app_secret, short_lived_token=short_lived_token)
        user_token_expires_at = utc_now() + timedelta(seconds=expires_in) if expires_in else None

        pages = await oauth_client.fetch_pages_with_tokens(user_access_token)
        ad_accounts = await oauth_client.fetch_ad_accounts(user_access_token)

        session_id = uuid4().hex
        session_payload = {
            "config_id": config_id,
            "user_access_token": user_access_token,
            "user_token_expires_at": user_token_expires_at.isoformat() if user_token_expires_at else None,
            "pages": pages,
            "ad_accounts": ad_accounts,
        }
        await self._redis.set(f"{META_OAUTH_SESSION_KEY_PREFIX}{session_id}", json.dumps(session_payload), ex=META_OAUTH_SESSION_TTL_SECONDS)
        return session_id

    async def _load_oauth_session(self, config_id: str, session_id: str) -> dict[str, Any]:
        raw = await self._redis.get(f"{META_OAUTH_SESSION_KEY_PREFIX}{session_id}")
        if raw is None:
            raise NotFoundError("This Facebook connection attempt has expired — click Connect Facebook again.")
        payload: dict[str, Any] = json.loads(raw)
        if payload["config_id"] != config_id:
            raise NotFoundError("This OAuth session does not belong to this configuration.")
        return payload

    async def get_oauth_session(self, config_id: str, session_id: str) -> OAuthSessionResponse:
        payload = await self._load_oauth_session(config_id, session_id)
        return OAuthSessionResponse(
            pages=[OAuthPageOption(id=p["id"], name=p["name"], instagram_username=p.get("instagram_username", "")) for p in payload["pages"]],
            ad_accounts=[OAuthAdAccountOption(id=a["id"], name=a["name"]) for a in payload["ad_accounts"]],
        )

    async def list_oauth_forms(self, config_id: str, session_id: str, page_id: str) -> list[OAuthFormOption]:
        payload = await self._load_oauth_session(config_id, session_id)
        page = next((p for p in payload["pages"] if p["id"] == page_id), None)
        if page is None:
            raise ValidationError("Unknown page_id for this OAuth session.")
        forms = await oauth_client.fetch_lead_forms(page_access_token=page["access_token"], page_id=page_id)
        return [OAuthFormOption(id=f["id"], name=f["name"]) for f in forms]

    async def connect_meta_oauth(self, config_id: str, session_id: str, payload: OAuthConnectRequest, actor: User) -> IntegrationConfig:
        session = await self._load_oauth_session(config_id, session_id)
        page = next((p for p in session["pages"] if p["id"] == payload.page_id), None)
        if page is None:
            raise ValidationError("Unknown page_id for this OAuth session.")
        if payload.ad_account_id and not any(a["id"] == payload.ad_account_id for a in session["ad_accounts"]):
            raise ValidationError("Unknown ad_account_id for this OAuth session.")

        page_access_token = page["access_token"]
        await oauth_client.subscribe_page_to_leadgen(page_access_token=page_access_token, page_id=page["id"])
        business_id = await oauth_client.fetch_page_business_id(page_access_token=page_access_token, page_id=page["id"])

        config = await self._require_meta_config(config_id)
        current = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        current.update(
            {
                # Same `access_token` key `testers.test_meta`/`meta_status.py`/
                # `lead_capture.meta_client.fetch_lead_fields` already read — a Page token
                # has `leads_retrieval` scoped to that Page, exactly what those need.
                "access_token": page_access_token,
                "user_access_token": session["user_access_token"],
                "user_token_expires_at": session["user_token_expires_at"] or "",
                "page_id": page["id"],
                "page_name": page["name"],
                "business_id": business_id or "",
                "ad_account_id": payload.ad_account_id or "",
                "selected_forms": ",".join(payload.selected_forms),
            }
        )
        await self._configs.update(
            config_id,
            {
                "config_encrypted": encrypt(json.dumps(current)), "is_enabled": True,
                # Credentials genuinely changed (new Page/token) — same reset
                # `update_config` already applies on a manual credential edit, so a stale
                # "last success" from a previous connection never keeps implying "still
                # connected."
                "is_active": False, "last_success_at": None, "health_status": None,
            },
            updated_by=actor.require_id(),
        )
        await self._redis.delete(f"{META_OAUTH_SESSION_KEY_PREFIX}{session_id}")
        await write_audit_log(self._db, event_type=AuditEvent.OAUTH_CONNECTED, user_id=actor.require_id(), metadata={"config_id": config_id, "page_id": page["id"]})

        # OAuth having just proven the credentials work is a stronger signal than a
        # manually-pasted token ever was — test then activate automatically so "Connect
        # Facebook" alone is enough to go live, the same destination the old manual
        # Test -> Enable -> Activate sequence reached, just driven by this one action.
        try:
            await self.test_connection(config_id, actor)
            await self.activate_config(config_id, actor)
        except ValidationError:
            pass  # left enabled-but-not-yet-active; Owner can retry Test/Activate from the details page, same recovery path as before OAuth existed

        return await self.get_config(config_id)

    async def sync_meta_forms(self, config_id: str) -> list[OAuthFormOption]:
        """"Sync Forms" on the Status panel — a manual refresh of the connected Page's
        Lead Forms using the already-stored Page Access Token, no new OAuth round trip
        required. Read-only: does not change `selected_forms`."""
        config = await self._require_meta_config(config_id)
        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        access_token, page_id = decrypted.get("access_token"), decrypted.get("page_id")
        if not access_token or not page_id:
            raise ValidationError("Connect Facebook first — no Page is linked to this configuration yet.")
        forms = await oauth_client.fetch_lead_forms(page_access_token=access_token, page_id=page_id)
        return [OAuthFormOption(id=f["id"], name=f["name"]) for f in forms]

    async def disconnect_meta(self, config_id: str, actor: User) -> IntegrationConfig:
        config = await self._require_meta_config(config_id)
        current = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        for key in ("access_token", "user_access_token", "user_token_expires_at", "page_id", "page_name", "business_id", "ad_account_id", "selected_forms"):
            current.pop(key, None)

        await self._configs.update(
            config_id,
            {"config_encrypted": encrypt(json.dumps(current)), "is_enabled": False, "is_active": False, "last_success_at": None, "health_status": None},
            updated_by=actor.require_id(),
        )
        await write_audit_log(self._db, event_type=AuditEvent.OAUTH_DISCONNECTED, user_id=actor.require_id(), metadata={"config_id": config_id})
        return await self.get_config(config_id)

    # ================================================================== token refresh (worker-driven, no human in the loop)

    async def refresh_expiring_meta_tokens(self) -> None:
        """Called from `worker/tasks/meta_token_refresh.py` once daily. Same "system
        action, no actor" posture as `LeadCaptureService.retry_due_failures` — `user_id=None`
        on the audit log, same as every other unattended job in this project."""
        configs = await self._configs.find_many({"integration_type": IntegrationType.META, "is_enabled": True}, limit=100)
        for config in configs:
            await self._refresh_one_meta_token(config)

    async def _refresh_one_meta_token(self, config: IntegrationConfig) -> None:
        decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
        app_id, app_secret = decrypted.get("app_id"), decrypted.get("app_secret")
        user_access_token, page_id = decrypted.get("user_access_token"), decrypted.get("page_id")
        expires_at_raw = decrypted.get("user_token_expires_at")
        if not (app_id and app_secret and user_access_token and page_id and expires_at_raw):
            return  # never OAuth-connected (or manually configured without a Page) — nothing to refresh

        expires_at = ensure_utc(datetime.fromisoformat(expires_at_raw))
        if expires_at - utc_now() > timedelta(days=META_TOKEN_REFRESH_WINDOW_DAYS):
            return  # not due yet

        config_id = config.require_id()
        try:
            new_user_token, expires_in = await oauth_client.exchange_for_long_lived_token(app_id=app_id, app_secret=app_secret, short_lived_token=user_access_token)
            new_page_token = await oauth_client.refresh_page_token(user_access_token=new_user_token, page_id=page_id)
            if not new_page_token:
                raise ValidationError("Meta did not return a refreshed Page Access Token.")
        except (httpx.HTTPError, ValidationError) as exc:
            # Read like any other failed health check — `_compute_health_status` already
            # treats a recent `last_failure_at` as ERROR, which is exactly right here: an
            # Owner needs to notice and reconnect before the old token actually expires.
            await self._configs.update(config_id, {"last_failure_at": utc_now(), "last_error_message": f"Token refresh failed: {exc}"})
            await write_audit_log(self._db, event_type=AuditEvent.TOKEN_REFRESH_FAILED, user_id=None, metadata={"config_id": config_id})
            return

        new_expires_at = utc_now() + timedelta(seconds=expires_in) if expires_in else None
        decrypted.update(
            {"access_token": new_page_token, "user_access_token": new_user_token, "user_token_expires_at": new_expires_at.isoformat() if new_expires_at else ""}
        )
        await self._configs.update(config_id, {"config_encrypted": encrypt(json.dumps(decrypted))})
        await write_audit_log(self._db, event_type=AuditEvent.TOKEN_REFRESHED, user_id=None, metadata={"config_id": config_id})
