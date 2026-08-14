"""Module 9C — Communication Engine routes. Originally an admin-only surface (Template
Management, Communication Queue, Delivery History, Failed Messages, Retry Action). Stage 3
(Geo Fencing/Temporary Permissions/MSG91 request) added: an individual "Send Message"
action for a Lead/Customer record (`send_crm_message`), a per-entity message history read
(`list_messages_for_entity`), and Bulk Messaging (`bulk-messages/*`) — the only endpoints
where a message is ever queued/sent outside `poll_business_events`' own worker-driven
path. Bulk sending is still never synchronous: `POST /communication/bulk-messages` only
creates a `BulkMessageJob`; the actual per-recipient enqueue happens in the worker-driven
`process_bulk_message_jobs` cron, and the actual provider send happens in the existing,
unchanged `process_pending_queue`/`process_retry_queue` cron jobs.

`public_router` (Stage 2 — MSG91 DLR webhook) is split out the same way `lead_capture`
splits its public webhook from its staff-only routes: MSG91's own servers cannot send a
Bearer token, so this one route can't sit behind `require_permission` — see
`receive_msg91_webhook`'s own docstring for how it's still kept safe.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.communication import mappers
from app.features.communication.dependencies import get_communication_service
from app.features.communication.schemas import (
    BulkMessageJobListResponse,
    BulkMessageJobResponse,
    CreateBulkMessageJobRequest,
    CreateTemplateRequest,
    HistoryResponse,
    QueueItemResponse,
    SendMessageRequest,
    SendMessageResponse,
    TemplateResponse,
    UpdateTemplateRequest,
)
from app.features.communication.service import CommunicationService
from app.middleware.rate_limit import rate_limited

logger = logging.getLogger(__name__)

router = APIRouter(tags=["communication"])
public_router = APIRouter(tags=["communication-public"])

ServiceDep = Annotated[CommunicationService, Depends(get_communication_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]
_MODULE = "communication"


def _perm(resource: str, action: str) -> Any:
    return require_permission(_MODULE, resource, action)


# ---------------------------------------------------------------------- templates


@router.post("/communication/templates")
async def create_template(payload: CreateTemplateRequest, service: ServiceDep, actor: Annotated[User, _perm("templates", "create")]) -> ApiResponse[TemplateResponse]:
    template = await service.create_template(payload, actor)
    return ApiResponse[TemplateResponse].ok(mappers.template_to_response(template))


@router.get("/communication/templates")
async def list_templates(
    service: ServiceDep, _actor: Annotated[User, _perm("templates", "view")], page: PageParamsDep,
    channel: str | None = None, category: str | None = None,
) -> ApiResponse[list[TemplateResponse]]:
    templates, total = await service.list_templates(channel=channel, category=category, skip=page.skip, limit=page.page_size, sort=page.sort)
    items = [mappers.template_to_response(t) for t in templates]
    return ApiResponse[list[TemplateResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/communication/templates/{template_id}")
async def get_template(template_id: str, service: ServiceDep, _actor: Annotated[User, _perm("templates", "view")]) -> ApiResponse[TemplateResponse]:
    template = await service.get_template(template_id)
    return ApiResponse[TemplateResponse].ok(mappers.template_to_response(template))


@router.patch("/communication/templates/{template_id}")
async def update_template(
    template_id: str, payload: UpdateTemplateRequest, service: ServiceDep, actor: Annotated[User, _perm("templates", "edit")]
) -> ApiResponse[TemplateResponse]:
    template = await service.update_template(template_id, payload, actor)
    return ApiResponse[TemplateResponse].ok(mappers.template_to_response(template))


# ---------------------------------------------------------------------- queue + failed messages


@router.get("/communication/queue")
async def list_queue(
    service: ServiceDep, _actor: Annotated[User, _perm("queue", "view")], page: PageParamsDep,
    status: str | None = None, channel: str | None = None,
) -> ApiResponse[list[QueueItemResponse]]:
    items, total = await service.list_queue(status=status, channel=channel, skip=page.skip, limit=page.page_size, sort=page.sort)
    responses = [mappers.queue_item_to_response(i) for i in items]
    return ApiResponse[list[QueueItemResponse]].ok(responses, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.post("/communication/queue/{queue_item_id}/retry")
async def retry_message(queue_item_id: str, service: ServiceDep, actor: Annotated[User, _perm("queue", "edit")]) -> ApiResponse[QueueItemResponse]:
    item = await service.retry_message_now(queue_item_id, actor)
    return ApiResponse[QueueItemResponse].ok(mappers.queue_item_to_response(item))


# ---------------------------------------------------------------------- delivery history


@router.get("/communication/history")
async def list_history(
    service: ServiceDep, _actor: Annotated[User, _perm("history", "view")], page: PageParamsDep,
    status: str | None = None, channel: str | None = None,
) -> ApiResponse[list[HistoryResponse]]:
    items, total = await service.list_history(status=status, channel=channel, skip=page.skip, limit=page.page_size, sort=page.sort)
    responses = [mappers.history_to_response(i) for i in items]
    return ApiResponse[list[HistoryResponse]].ok(responses, meta=ResponseMeta(pagination=page.build_meta(total)))


# ---------------------------------------------------------------------- CRM record messaging (Stage 3)


@router.post("/communication/messages")
async def send_crm_message(payload: SendMessageRequest, service: ServiceDep, actor: Annotated[User, _perm("send", "create")]) -> ApiResponse[SendMessageResponse]:
    """The recipient is always resolved server-side from the authorized Lead/Customer
    record — `payload` never carries a raw phone number/email (see
    `CommunicationService.send_crm_message`'s own IDOR/authorization checks)."""
    success, queue_item_id, error = await service.send_crm_message(
        entity_type=payload.entity_type, entity_id=payload.entity_id, channel=payload.channel,
        template_id=payload.template_id, actor=actor, extra_variables=payload.variables,
    )
    status = "sent" if success else ("failed" if queue_item_id is not None else None)
    return ApiResponse[SendMessageResponse].ok(SendMessageResponse(success=success, queue_item_id=queue_item_id, status=status, error=error))


@router.get("/communication/messages")
async def list_entity_messages(
    service: ServiceDep, actor: Annotated[User, _perm("send", "view")], entity_type: str, entity_id: str,
) -> ApiResponse[list[QueueItemResponse]]:
    items = await service.list_messages_for_entity(entity_type=entity_type, entity_id=entity_id, actor=actor)
    return ApiResponse[list[QueueItemResponse]].ok([mappers.queue_item_to_response(i) for i in items])


# ---------------------------------------------------------------------- bulk messaging (Stage 3)


@router.post("/communication/bulk-messages")
async def create_bulk_message_job(
    payload: CreateBulkMessageJobRequest, service: ServiceDep, actor: Annotated[User, _perm("bulk", "create")]
) -> ApiResponse[BulkMessageJobResponse]:
    job = await service.create_bulk_message_job(
        channel=payload.channel, template_id=payload.template_id, recipient_type=payload.recipient_type,
        recipient_ids=payload.recipient_ids, actor=actor,
    )
    progress = await service.bulk_job_progress(job.require_id())
    return ApiResponse[BulkMessageJobResponse].ok(mappers.bulk_job_to_response(job, progress))


@router.get("/communication/bulk-messages")
async def list_bulk_message_jobs(
    service: ServiceDep, _actor: Annotated[User, _perm("bulk", "view")], page: PageParamsDep,
) -> ApiResponse[list[BulkMessageJobListResponse]]:
    jobs, total = await service.list_bulk_message_jobs(skip=page.skip, limit=page.page_size)
    items = [mappers.bulk_job_to_list_response(j) for j in jobs]
    return ApiResponse[list[BulkMessageJobListResponse]].ok(items, meta=ResponseMeta(pagination=page.build_meta(total)))


@router.get("/communication/bulk-messages/{job_id}")
async def get_bulk_message_job(job_id: str, service: ServiceDep, _actor: Annotated[User, _perm("bulk", "view")]) -> ApiResponse[BulkMessageJobResponse]:
    job = await service.get_bulk_message_job(job_id)
    progress = await service.bulk_job_progress(job_id)
    return ApiResponse[BulkMessageJobResponse].ok(mappers.bulk_job_to_response(job, progress))


@router.get("/communication/bulk-messages/{job_id}/failed")
async def list_bulk_message_job_failed(
    job_id: str, service: ServiceDep, _actor: Annotated[User, _perm("bulk", "view")]
) -> ApiResponse[list[QueueItemResponse]]:
    items = await service.list_bulk_job_failed_messages(job_id)
    return ApiResponse[list[QueueItemResponse]].ok([mappers.queue_item_to_response(i) for i in items])


@router.post("/communication/bulk-messages/{job_id}/retry-failed")
async def retry_bulk_message_job_failed(
    job_id: str, service: ServiceDep, actor: Annotated[User, _perm("bulk", "edit")]
) -> ApiResponse[dict[str, int]]:
    retried_count = await service.retry_bulk_job_failed(job_id, actor)
    return ApiResponse[dict[str, int]].ok({"retried_count": retried_count})


@router.post("/communication/bulk-messages/{job_id}/cancel")
async def cancel_bulk_message_job(
    job_id: str, service: ServiceDep, actor: Annotated[User, _perm("bulk", "edit")]
) -> ApiResponse[BulkMessageJobResponse]:
    job = await service.cancel_bulk_message_job(job_id, actor)
    progress = await service.bulk_job_progress(job_id)
    return ApiResponse[BulkMessageJobResponse].ok(mappers.bulk_job_to_response(job, progress))


# ---------------------------------------------------------------------- public: MSG91 delivery webhook (Stage 2)

# SMS DLR status codes, per MSG91's own webhook documentation (docs.msg91.com /
# msg91.com/help/webhook-new — see docs/COMMUNICATION.md for what was and wasn't
# confirmable in this environment): 0=Sent, 1=Delivered, 2=Failed, 9=NDNC,
# 16/25=Rejected, 17=Blocked, 20=Country blocked. WhatsApp's own DLR status field names
# were not independently confirmed against official docs in this environment — see
# docs/KNOWN_LIMITATIONS.md's Module 10/Communication section — so a WhatsApp callback
# using different field names is safely ignored (malformed-payload path) rather than
# mis-parsed.
_MSG91_DELIVERED_STATUS_CODES = {1}
_MSG91_FAILED_STATUS_CODES = {2, 9, 16, 17, 20, 25}


@public_router.post("/communication/webhooks/msg91", dependencies=[rate_limited(limit=120)])
async def receive_msg91_webhook(request: Request, service: ServiceDep, secret: Annotated[str | None, Query()] = None) -> Response:
    """MSG91's own servers call this with no Bearer token available — kept safe via a
    shared secret configured on the MSG91 integration and appended to the webhook URL
    entered in MSG91's dashboard (`?secret=...`), not `require_permission`/JWT (see
    `CommunicationService.verify_msg91_webhook_secret`'s own docstring for why a secret-
    in-URL is the honest choice here, not a cryptographic signature). Never marks a
    message "Delivered" just because MSG91 accepted the original send request — that
    already happened at send time (`QueueStatus.SENT`); only this webhook, a genuine
    third-party delivery confirmation, advances it to `DELIVERED`. Always responds within
    MSG91's stated retry/auto-pause window: 200 for anything processed (including an
    unknown/duplicate message id, which is expected and benign, not an error), 403 for a
    missing/wrong secret, 400 only for a malformed body (MSG91 auto-pauses a webhook URL
    that keeps 4xx-ing, so this is reserved for genuinely bad requests, not business-logic
    outcomes)."""
    verified = await service.verify_msg91_webhook_secret(secret)
    if not verified:
        logger.warning("MSG91 webhook rejected — missing or invalid secret.")
        return Response(status_code=403)

    try:
        payload = await request.json()
    except ValueError:
        logger.warning("MSG91 webhook rejected — malformed (non-JSON) body.")
        return Response(status_code=400)
    if not isinstance(payload, dict):
        logger.warning("MSG91 webhook rejected — body is not a JSON object.")
        return Response(status_code=400)

    request_id = payload.get("requestId")
    raw_status = payload.get("status")
    if not request_id or raw_status is None:
        logger.warning("MSG91 webhook rejected — missing requestId/status field(s).")
        return Response(status_code=400)

    try:
        status_code = int(raw_status)
    except (TypeError, ValueError):
        logger.warning("MSG91 webhook rejected — non-numeric status field: %r", raw_status)
        return Response(status_code=400)

    outcome = await service.process_delivery_webhook(
        provider="msg91", provider_message_id=str(request_id), delivered=status_code in _MSG91_DELIVERED_STATUS_CODES,
        failed=status_code in _MSG91_FAILED_STATUS_CODES, error=f"MSG91 delivery status {status_code}" if status_code in _MSG91_FAILED_STATUS_CODES else None,
    )
    logger.info("MSG91 webhook processed: requestId=%s status=%s outcome=%s", request_id, status_code, outcome)
    return Response(status_code=200)
