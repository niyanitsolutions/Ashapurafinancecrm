from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationProviderResponse(BaseModel):
    id: str
    integration_type: str
    provider: str
    label: str


class CreateIntegrationConfigRequest(BaseModel):
    integration_type: str
    provider: str
    name: str
    config: dict[str, str] = Field(default_factory=dict)


class UpdateIntegrationConfigRequest(BaseModel):
    name: str | None = None
    # Merged into the existing decrypted config, not replaced wholesale — same pattern
    # as system_settings.ApiSetting, so rotating one key never requires resupplying
    # every other secret.
    config: dict[str, str] | None = None


class IntegrationConfigResponse(BaseModel):
    id: str
    integration_code: str
    integration_type: str
    provider: str
    name: str
    # Secret-looking keys (decision — see constants.py:is_secret_key) are masked to
    # their last 4 characters, same convention as Employee's bank account masking.
    # Never the raw decrypted value.
    config: dict[str, str]
    is_enabled: bool
    is_active: bool
    last_tested_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error_message: str | None
    activated_at: datetime | None
    webhook_verified_at: datetime | None
    health_status: str | None
    created_at: datetime
    updated_at: datetime
    # Only populated on the response to `POST /integration-configs` for a freshly-created
    # Meta config with auto-generated webhook credentials — the one moment the Owner needs
    # the *path* to paste alongside the plaintext values `config` reveals for that same
    # response (see mappers.config_to_response's `reveal` param). Every other read masks
    # these fields as usual and this stays `None`.
    webhook_callback_path: str | None = None


class ConnectionCheckItemResponse(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    response_time_ms: int
    error_message: str | None
    tested_at: datetime
    # Meta only — the individual App ID/App Secret/Token/Permissions checks. `None` for
    # every other integration_type (WhatsApp/SMS/Email/Maps testers don't populate this).
    checks: list[ConnectionCheckItemResponse] | None = None


class TestDraftConnectionRequest(BaseModel):
    """Tests raw credentials before any `IntegrationConfig` row exists — same tester
    dispatch as the real `/test` endpoint, but nothing is persisted (no config, no
    IntegrationTestLog): lets the Owner prove credentials work before committing to Save."""

    integration_type: str
    config: dict[str, str] = Field(default_factory=dict)


class IntegrationTestLogResponse(BaseModel):
    id: str
    success: bool
    response_time_ms: int
    error_message: str | None
    tested_at: datetime
    graph_api_version: str | None = None
    tested_ip: str | None = None


class SetupProgressResponse(BaseModel):
    credentials_entered: bool
    test_connection_passed: bool
    saved: bool
    activated: bool
    webhook_verified: bool
    first_lead_received: bool


class MissingPermissionResponse(BaseModel):
    permission: str
    why_needed: str


class MetaStatusResponse(BaseModel):
    health_status: str | None
    setup_progress: SetupProgressResponse
    completed_steps: int
    total_steps: int
    ad_accounts_count: int | None
    pages_count: int | None
    lead_forms_count: int | None
    webhook_verified_at: datetime | None
    last_lead_received_at: datetime | None
    total_leads_imported: int
    connected_since: datetime | None
    missing_permissions: list[MissingPermissionResponse]
    token_expires_at: datetime | None
    belongs_to_app_name: str | None
    graph_api_version: str
    # Meta-only, OAuth-only — the long-lived User Token's own expiry (what
    # `worker/tasks/meta_token_refresh.py` actually watches) and when it was last
    # refreshed, so an Owner can tell "is this about to need reconnecting" without
    # reading server logs. `None` for a manually-pasted-token config (no OAuth ever ran).
    user_token_expires_at: datetime | None = None
    last_token_refresh_at: datetime | None = None
    connected_page_name: str | None = None
    connected_ad_account_id: str | None = None
    connected_form_count: int | None = None  # None means "all forms on the Page" (no filter set)


class OAuthLoginResponse(BaseModel):
    authorize_url: str


class OAuthPageOption(BaseModel):
    id: str
    name: str
    # Non-empty only when this Page has a linked Instagram Business Account — Instagram
    # Lead Ads share this same Page's leadgen webhook subscription, so there is no
    # separate Instagram picker step, just this visibility into which Page also covers it.
    instagram_username: str = ""


class OAuthAdAccountOption(BaseModel):
    id: str
    name: str


class OAuthFormOption(BaseModel):
    id: str
    name: str


class OAuthSessionResponse(BaseModel):
    pages: list[OAuthPageOption]
    ad_accounts: list[OAuthAdAccountOption]


class OAuthConnectRequest(BaseModel):
    page_id: str
    ad_account_id: str | None = None
    selected_forms: list[str] = Field(default_factory=list)
