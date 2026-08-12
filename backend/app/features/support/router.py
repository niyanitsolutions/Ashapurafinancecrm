from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.support import mappers
from app.features.support.dependencies import (
    CurrentUserDep,
    get_support_ticket_service,
    require_customer,
)
from app.features.support.schemas import (
    AttachmentUploadUrlRequest,
    AttachmentUploadUrlResponse,
    CreateSupportTicketRequest,
    SupportTicketResponse,
)
from app.features.support.service import SupportTicketService

router = APIRouter(prefix="/support-tickets", tags=["support"])

ServiceDep = Annotated[SupportTicketService, Depends(get_support_ticket_service)]
CustomerDep = Annotated[User, Depends(require_customer)]


@router.post("/attachment-upload-url")
async def get_attachment_upload_url(
    payload: AttachmentUploadUrlRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[AttachmentUploadUrlResponse]:
    url, s3_key = await service.get_attachment_upload_url(payload.file_name, payload.content_type, current_user)
    return ApiResponse[AttachmentUploadUrlResponse].ok(AttachmentUploadUrlResponse(upload_url=url, s3_key=s3_key))


@router.post("")
async def create_ticket(
    payload: CreateSupportTicketRequest, service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[SupportTicketResponse]:
    ticket = await service.create_ticket(payload, current_user)
    return ApiResponse[SupportTicketResponse].ok(mappers.ticket_to_response(ticket, service.attachment_download_url(ticket)))


@router.get("/me")
async def list_own_tickets(
    service: ServiceDep, current_user: CurrentUserDep, _customer: CustomerDep
) -> ApiResponse[list[SupportTicketResponse]]:
    tickets = await service.list_own_tickets(current_user)
    items = [mappers.ticket_to_response(t, service.attachment_download_url(t)) for t in tickets]
    return ApiResponse[list[SupportTicketResponse]].ok(items)
