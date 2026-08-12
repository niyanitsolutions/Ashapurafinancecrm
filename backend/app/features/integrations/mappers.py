import json
from datetime import datetime

from app.features.integrations.constants import is_secret_key
from app.features.integrations.models import (
    IntegrationConfig,
    IntegrationProvider,
    IntegrationTestLog,
)
from app.features.integrations.schemas import (
    ConnectionCheckItemResponse,
    IntegrationConfigResponse,
    IntegrationProviderResponse,
    IntegrationTestLogResponse,
    TestConnectionResponse,
)
from app.features.integrations.testers import ConnectionCheckResult
from app.security.encryption import decrypt


def mask_secret(plaintext: str) -> str:
    # Same convention as Employee.mask_account_number (decision 018) — last 4 characters
    # visible, never the full value.
    return f"{'*' * max(0, len(plaintext) - 4)}{plaintext[-4:]}"


def mask_config(config: dict[str, str]) -> dict[str, str]:
    return {key: (mask_secret(value) if is_secret_key(key) else value) for key, value in config.items()}


def provider_to_response(provider: IntegrationProvider) -> IntegrationProviderResponse:
    return IntegrationProviderResponse(id=provider.require_id(), integration_type=provider.integration_type, provider=provider.provider, label=provider.label)


def config_to_response(config: IntegrationConfig, *, reveal: dict[str, str] | None = None, webhook_callback_path: str | None = None) -> IntegrationConfigResponse:
    decrypted = json.loads(decrypt(config.config_encrypted)) if config.config_encrypted else {}
    masked = mask_config(decrypted)
    # `reveal` is only ever passed by the create-config route, immediately after
    # `IntegrationsService.create_config` auto-generates Meta's webhook credentials —
    # this is the one response where the Owner needs the plaintext to paste into Meta's
    # Webhook product setup. Every other call site (list/get/update) omits it and these
    # keys stay masked like any other secret.
    if reveal:
        masked = {**masked, **reveal}
    return IntegrationConfigResponse(
        id=config.require_id(), integration_code=config.integration_code, integration_type=config.integration_type, provider=config.provider,
        name=config.name, config=masked, is_enabled=config.is_enabled, is_active=config.is_active,
        last_tested_at=config.last_tested_at, last_success_at=config.last_success_at, last_failure_at=config.last_failure_at,
        last_error_message=config.last_error_message, activated_at=config.activated_at, webhook_verified_at=config.webhook_verified_at,
        health_status=config.health_status, created_at=config.created_at, updated_at=config.updated_at, webhook_callback_path=webhook_callback_path,
    )


def test_log_to_response(log: IntegrationTestLog) -> IntegrationTestLogResponse:
    return IntegrationTestLogResponse(
        id=log.require_id(), success=log.success, response_time_ms=log.response_time_ms, error_message=log.error_message,
        tested_at=log.tested_at, graph_api_version=log.graph_api_version, tested_ip=log.tested_ip,
    )


def test_result_to_response(outcome: ConnectionCheckResult, tested_at: datetime) -> TestConnectionResponse:
    checks = (
        [ConnectionCheckItemResponse(key=c.key, label=c.label, passed=c.passed, detail=c.detail) for c in outcome.checks]
        if outcome.checks is not None
        else None
    )
    return TestConnectionResponse(
        success=outcome.success, response_time_ms=outcome.response_time_ms, error_message=outcome.error_message,
        tested_at=tested_at, checks=checks,
    )
