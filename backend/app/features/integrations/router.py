"""Module 9A — API Management routes. Every endpoint is `require_permission("integrations",
"configs", action)` — real, Owner-delegable Access Control permissions, reusing the
platform rather than a bespoke role check, per explicit instruction.

`public_router` holds exactly one route — the Meta OAuth callback — split out the same
way `lead_capture` splits its public webhook routes from its staff-only ones: Facebook's
own server redirects the browser here with no `Authorization` header available (the SPA
is Bearer-token-only, see `frontend/src/shared/api/client.ts`), so this one route can't
sit behind `require_permission`. It's still safe: `IntegrationsService.handle_meta_oauth_callback`
verifies the CSRF `state` against Redis before doing anything.
"""

import json
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.config.settings import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.dependencies import get_request_context
from app.features.auth.models import User
from app.features.auth.service import RequestContext
from app.features.integrations import mappers
from app.features.integrations.dependencies import get_integrations_service
from app.features.integrations.schemas import (
    CreateIntegrationConfigRequest,
    IntegrationConfigResponse,
    IntegrationProviderResponse,
    IntegrationTestLogResponse,
    MetaStatusResponse,
    OAuthConnectRequest,
    OAuthFormOption,
    OAuthLoginResponse,
    OAuthSessionResponse,
    TestConnectionResponse,
    TestDraftConnectionRequest,
    UpdateIntegrationConfigRequest,
)
from app.features.integrations.service import IntegrationsService
from app.security.encryption import decrypt

router = APIRouter(tags=["integrations"])
public_router = APIRouter(tags=["integrations-public"])

ServiceDep = Annotated[IntegrationsService, Depends(get_integrations_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]
_MODULE = "integrations"
_RESOURCE = "configs"


def _perm(action: str) -> Any:
    return require_permission(_MODULE, _RESOURCE, action)


@router.get("/integration-providers")
async def list_providers(service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[list[IntegrationProviderResponse]]:
    providers = await service.list_providers()
    return ApiResponse[list[IntegrationProviderResponse]].ok([mappers.provider_to_response(p) for p in providers])


@router.post("/integration-configs")
async def create_config(payload: CreateIntegrationConfigRequest, service: ServiceDep, actor: Annotated[User, _perm("create")]) -> ApiResponse[IntegrationConfigResponse]:
    config, generated = await service.create_config(payload, actor)
    # `generated` is only non-empty for a brand-new Meta config whose Webhook Verify
    # Token/Secret weren't supplied — this is the one response where the Owner sees the
    # plaintext, to paste into Meta's Webhook product setup; see mappers.config_to_response.
    webhook_callback_path = "/lead-capture/webhooks/meta" if generated else None
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config, reveal=generated or None, webhook_callback_path=webhook_callback_path))


@router.get("/integration-configs")
async def list_configs(
    service: ServiceDep, _actor: Annotated[User, _perm("view")], page: PageParamsDep, integration_type: str | None = None
) -> ApiResponse[list[IntegrationConfigResponse]]:
    configs, total = await service.list_configs(integration_type=integration_type, skip=page.skip, limit=page.page_size, sort=page.sort)
    items = [mappers.config_to_response(c) for c in configs]
    return ApiResponse[list[IntegrationConfigResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/integration-configs/{config_id}")
async def get_config(config_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.get_config(config_id)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.patch("/integration-configs/{config_id}")
async def update_config(
    config_id: str, payload: UpdateIntegrationConfigRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.update_config(config_id, payload, actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.patch("/integration-configs/{config_id}/enable")
async def enable_config(config_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.set_enabled(config_id, enabled=True, actor=actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.patch("/integration-configs/{config_id}/disable")
async def disable_config(config_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.set_enabled(config_id, enabled=False, actor=actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.post("/integration-configs/{config_id}/activate")
async def activate_config(config_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.activate_config(config_id, actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.post("/integration-configs/{config_id}/test")
async def test_connection(
    config_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")], ctx: RequestContextDep
) -> ApiResponse[TestConnectionResponse]:
    result = await service.test_connection(config_id, actor, ip_address=ctx.ip_address)
    return ApiResponse[TestConnectionResponse].ok(result)


@router.post("/integration-configs/test-draft")
async def test_draft_connection(
    payload: TestDraftConnectionRequest, service: ServiceDep, _actor: Annotated[User, _perm("create")]
) -> ApiResponse[TestConnectionResponse]:
    result = await service.test_draft_connection(payload)
    return ApiResponse[TestConnectionResponse].ok(result)


@router.get("/integration-configs/{config_id}/test-logs")
async def list_test_logs(config_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[list[IntegrationTestLogResponse]]:
    logs = await service.list_test_logs(config_id)
    return ApiResponse[list[IntegrationTestLogResponse]].ok([mappers.test_log_to_response(log) for log in logs])


@router.get("/integration-configs/{config_id}/meta-status")
async def get_meta_status(config_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[MetaStatusResponse]:
    result = await service.get_meta_status(config_id)
    return ApiResponse[MetaStatusResponse].ok(result)


# ---------------------------------------------------------------------- Meta OAuth Connect flow


@router.get("/integration-configs/{config_id}/oauth/login")
async def start_oauth_login(config_id: str, request: Request, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[OAuthLoginResponse]:
    redirect_uri = str(request.url_for("receive_oauth_callback"))
    authorize_url = await service.start_meta_oauth(config_id, actor, redirect_uri=redirect_uri)
    return ApiResponse[OAuthLoginResponse].ok(OAuthLoginResponse(authorize_url=authorize_url))


@router.get("/integration-configs/{config_id}/oauth/session/{session_id}")
async def get_oauth_session(config_id: str, session_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[OAuthSessionResponse]:
    result = await service.get_oauth_session(config_id, session_id)
    return ApiResponse[OAuthSessionResponse].ok(result)


@router.get("/integration-configs/{config_id}/oauth/session/{session_id}/forms")
async def list_oauth_forms(
    config_id: str, session_id: str, page_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]
) -> ApiResponse[list[OAuthFormOption]]:
    forms = await service.list_oauth_forms(config_id, session_id, page_id)
    return ApiResponse[list[OAuthFormOption]].ok(forms)


@router.post("/integration-configs/{config_id}/oauth/session/{session_id}/connect")
async def connect_oauth_session(
    config_id: str, session_id: str, payload: OAuthConnectRequest, service: ServiceDep, actor: Annotated[User, _perm("edit")]
) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.connect_meta_oauth(config_id, session_id, payload, actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@router.get("/integration-configs/{config_id}/oauth/forms")
async def sync_oauth_forms(config_id: str, service: ServiceDep, _actor: Annotated[User, _perm("view")]) -> ApiResponse[list[OAuthFormOption]]:
    """"Sync Forms" on the Status panel — re-fetches the connected Page's Lead Forms
    using the already-stored token, distinct from `oauth/session/{id}/forms` which only
    exists during the initial Connect picker."""
    forms = await service.sync_meta_forms(config_id)
    return ApiResponse[list[OAuthFormOption]].ok(forms)


@router.post("/integration-configs/{config_id}/oauth/disconnect")
async def disconnect_oauth(config_id: str, service: ServiceDep, actor: Annotated[User, _perm("edit")]) -> ApiResponse[IntegrationConfigResponse]:
    config = await service.disconnect_meta(config_id, actor)
    return ApiResponse[IntegrationConfigResponse].ok(mappers.config_to_response(config))


@public_router.get("/integration-configs/oauth/callback")
async def receive_oauth_callback(request: Request, service: ServiceDep) -> RedirectResponse:
    """Facebook's own redirect target — no bearer token available here (see module
    docstring). Every outcome (denied login, expired/invalid state, a Graph API failure,
    or success) ends in a redirect back to the SPA; nothing is ever returned as raw JSON
    since a browser navigation, not a `fetch`, lands here.
    """
    settings = get_settings()
    redirect_uri = str(request.url_for("receive_oauth_callback"))
    state = request.query_params.get("state") or ""
    code = request.query_params.get("code")

    fallback_config_id: str | None = None
    try:
        fallback_config_id = json.loads(decrypt(state)).get("config_id") if state else None
    except Exception:  # noqa: BLE001 - state is attacker-controlled input; any decode failure just means "unknown config"
        fallback_config_id = None

    def _redirect(config_id: str | None, **params: str) -> RedirectResponse:
        target = f"{settings.frontend_base_url}/integrations/{config_id}" if config_id else f"{settings.frontend_base_url}/integrations"
        return RedirectResponse(url=f"{target}?{urlencode(params)}" if params else target, status_code=307)

    if not code:
        error = request.query_params.get("error_description") or request.query_params.get("error") or "Facebook login was cancelled."
        return _redirect(fallback_config_id, oauth_error=error)

    try:
        session_id = await service.handle_meta_oauth_callback(code=code, state=state, redirect_uri=redirect_uri)
    except (ValidationError, NotFoundError) as exc:
        return _redirect(fallback_config_id, oauth_error=str(exc))
    except httpx.HTTPError as exc:
        return _redirect(fallback_config_id, oauth_error=f"Facebook request failed: {exc}")

    return _redirect(fallback_config_id, oauth_session=session_id)
