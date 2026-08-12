"""Module 9B — Lead Capture routes, split the same way Module 6B split public vs.
authenticated endpoints: `public_router` (Website form submission, Meta webhook — no
JWT, since the caller is an external website visitor or Meta's own servers) and
`router` (Manual API capture, Source Mapping, Capture Failures — staff, permission-gated).

Neither `public_router` route declares any `Depends(get_current_user)`/permission
dependency, nor is there any global auth middleware in `app/main.py` (auth is enforced
per-route via `Depends`, never globally — see `middleware/` for the only app-wide
middlewares: CORS, request-id, security headers, and request logging, none of which
gate on authentication). Meta's own servers cannot send an `Authorization` header, a
cookie, or a CSRF token, and none of those are required here — confirmed by inspection,
not assumed, while diagnosing the webhook verification 403 (see `verify_meta_webhook`'s
own docstring for that root cause).
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.integrations import mappers as integrations_mappers
from app.features.lead_capture import mappers
from app.features.lead_capture.dependencies import get_lead_capture_service
from app.features.lead_capture.schemas import (
    CaptureFailureResponse,
    CaptureSourceResponse,
    ManualCaptureRequest,
    UpdateCaptureSourceRequest,
    WebsiteCaptureRequest,
    WebsiteCaptureResponse,
)
from app.features.lead_capture.service import LeadCaptureService
from app.middleware.rate_limit import rate_limited

logger = logging.getLogger(__name__)

public_router = APIRouter(tags=["lead-capture-public"])
router = APIRouter(tags=["lead-capture"])

ServiceDep = Annotated[LeadCaptureService, Depends(get_lead_capture_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "lead_capture"


def _perm(resource: str, action: str) -> Any:
    return require_permission(_MODULE, resource, action)


# ---------------------------------------------------------------------- public: website form


@public_router.post("/lead-capture/website", dependencies=[rate_limited(limit=20)])
async def capture_website_lead(payload: WebsiteCaptureRequest, service: ServiceDep) -> ApiResponse[WebsiteCaptureResponse]:
    lead = await service.capture_from_website(payload)
    return ApiResponse[WebsiteCaptureResponse].ok(WebsiteCaptureResponse(status="created", lead_code=lead.lead_code))


# ---------------------------------------------------------------------- public: Meta webhook


@public_router.get("/lead-capture/webhooks/meta")
async def verify_meta_webhook(
    service: ServiceDep,
    # Meta sends dotted query keys (`hub.mode`, not `hub_mode`) — a bare Python parameter
    # name can never contain a dot, so `Query(alias=...)` is what makes FastAPI bind
    # `hub_mode` to the literal `hub.mode` query string key. This also makes the three
    # parameters show up correctly in the OpenAPI schema/Swagger UI, instead of being
    # invisible raw `request.query_params` reads.
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
) -> Response:
    """Meta's webhook verification handshake — see Meta's own docs:
    https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests

    ROOT CAUSE of the reported 403 (fixed in `LeadCaptureService.verify_meta_challenge`,
    see its docstring): that method used to look up only the currently `is_active` Meta
    `IntegrationConfig`, which is never true yet at the point Meta actually calls this
    endpoint — a fresh config isn't active until *after* a full OAuth Connect, so the
    very first "Verify and Save" click in Meta's dashboard always found no config and
    always 403'd, regardless of how correct the pasted Verify Token was. That method now
    checks every configured Meta credential set, not just the active one.

    Response contract, exactly as Meta requires: a bare `hub.challenge` echoed back as
    `text/plain` on success — no JSON envelope, no quotes (`PlainTextResponse` is used
    here instead of this module's usual `ApiResponse` envelope for that reason) — 403 on
    a token mismatch, 400 if this isn't even a `subscribe` verification request at all.
    """
    logger.info(
        "Meta webhook GET verification request: hub.mode=%s hub.challenge_present=%s hub.verify_token=%s",
        hub_mode, hub_challenge is not None, integrations_mappers.mask_secret(hub_verify_token) if hub_verify_token else "(none)",
    )

    if hub_mode != "subscribe":
        # Not a verification request this endpoint understands (Meta only ever sends
        # "subscribe" for this callback type) — 400, distinct from a 403 token mismatch,
        # since there's no token to have gotten wrong in the first place.
        logger.warning("Meta webhook GET called with unsupported or missing hub.mode=%r — returning 400.", hub_mode)
        return Response(status_code=400)

    verified = await service.verify_meta_challenge(mode=hub_mode, verify_token=hub_verify_token)
    if not verified or hub_challenge is None:
        logger.warning("Meta webhook verification failed (no matching webhook_verify_token) — returning 403.")
        return Response(status_code=403)

    logger.info("Meta webhook verification succeeded — echoing hub.challenge back as plain text (200).")
    return PlainTextResponse(hub_challenge)


@public_router.post("/lead-capture/webhooks/meta", dependencies=[rate_limited(limit=120)])
async def receive_meta_webhook(request: Request, service: ServiceDep) -> Response:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    logger.info("Meta webhook POST received: content_length=%s signature_present=%s", len(raw_body), signature is not None)
    verified = await service.handle_meta_webhook(raw_body, signature)
    if not verified:
        logger.warning("Meta webhook POST rejected — no active Meta config or invalid X-Hub-Signature-256 (returning 403).")
        return Response(status_code=403)
    logger.info("Meta webhook POST processed and acknowledged (200).")
    return Response(status_code=200)  # always ack once verified — Meta's own retry contract is not what drives our retry queue


# ---------------------------------------------------------------------- staff: manual API capture


@router.post("/lead-capture/manual")
async def capture_manual_lead(
    payload: ManualCaptureRequest, service: ServiceDep, actor: Annotated[User, _perm("captures", "create")]
) -> ApiResponse[dict[str, str]]:
    lead = await service.capture_manual(payload, actor)
    return ApiResponse[dict[str, str]].ok({"lead_code": lead.lead_code, "lead_id": lead.require_id()})


# ---------------------------------------------------------------------- staff: source mapping


@router.get("/lead-capture/sources")
async def list_capture_sources(service: ServiceDep, _actor: Annotated[User, _perm("sources", "view")]) -> ApiResponse[list[CaptureSourceResponse]]:
    sources = await service.list_sources()
    return ApiResponse[list[CaptureSourceResponse]].ok([mappers.source_to_response(s) for s in sources])


@router.patch("/lead-capture/sources/{key}")
async def update_capture_source(
    key: str, payload: UpdateCaptureSourceRequest, service: ServiceDep, actor: Annotated[User, _perm("sources", "edit")]
) -> ApiResponse[CaptureSourceResponse]:
    source = await service.update_source(key, payload, actor)
    return ApiResponse[CaptureSourceResponse].ok(mappers.source_to_response(source))


# ---------------------------------------------------------------------- staff: capture failures + retry


@router.get("/lead-capture/failures")
async def list_capture_failures(
    service: ServiceDep, _actor: Annotated[User, _perm("failures", "view")], page: PageParamsDep,
    capture_source: str | None = None, status: str | None = None, failure_reason: str | None = None,
) -> ApiResponse[list[CaptureFailureResponse]]:
    failures, total = await service.list_failures(
        capture_source=capture_source, status=status, failure_reason=failure_reason, skip=page.skip, limit=page.page_size, sort=page.sort
    )
    items = [mappers.failure_to_response(f) for f in failures]
    return ApiResponse[list[CaptureFailureResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("/lead-capture/failures/{failure_id}/retry")
async def retry_capture_failure(failure_id: str, service: ServiceDep, _actor: Annotated[User, _perm("failures", "edit")]) -> ApiResponse[CaptureFailureResponse]:
    failure = await service.retry_failure_now(failure_id)
    return ApiResponse[CaptureFailureResponse].ok(mappers.failure_to_response(failure))
