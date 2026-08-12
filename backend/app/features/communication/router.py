"""Module 9C — Communication Engine routes. Admin-only surface, per explicit scope:
Template Management, Communication Queue, Delivery History, Failed Messages, Retry
Action. No campaign builder, no bulk messaging, no manual "send now" endpoint — every
queue item is created only by `CommunicationService.poll_business_events` (worker-driven).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.pagination import PageParams, page_params
from app.core.response import ApiResponse, ResponseMeta
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.communication import mappers
from app.features.communication.dependencies import get_communication_service
from app.features.communication.schemas import (
    CreateTemplateRequest,
    HistoryResponse,
    QueueItemResponse,
    TemplateResponse,
    UpdateTemplateRequest,
)
from app.features.communication.service import CommunicationService

router = APIRouter(tags=["communication"])

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
