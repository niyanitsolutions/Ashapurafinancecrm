from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
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
    RespondToTicketRequest,
    SupportTicketResponse,
)
from app.features.support.service import SupportTicketService

router = APIRouter(prefix="/support-tickets", tags=["support"])

ServiceDep = Annotated[SupportTicketService, Depends(get_support_ticket_service)]
CustomerDep = Annotated[User, Depends(require_customer)]


def _staff_perm(action: str) -> Any:
    return require_permission("support", "tickets", action)


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


# ---------------------------------------------------------------- staff resolution workflow


@router.get("")
async def list_all_tickets(
    service: ServiceDep, actor: Annotated[User, _staff_perm("view")], status: str | None = None, search: str | None = None
) -> ApiResponse[list[SupportTicketResponse]]:
    tickets = await service.list_all_tickets(actor, status=status, search=search)
    assigned_to_name, responded_by_name = await service.resolve_staff_names(tickets)
    items = [
        mappers.ticket_to_response(
            t, service.attachment_download_url(t),
            assigned_to_name=assigned_to_name.get(t.assigned_to or ""),
            responded_by_name=responded_by_name.get(t.responded_by or ""),
        )
        for t in tickets
    ]
    return ApiResponse[list[SupportTicketResponse]].ok(items)


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, service: ServiceDep, actor: Annotated[User, _staff_perm("view")]) -> ApiResponse[SupportTicketResponse]:
    ticket = await service.get_ticket_for_staff(ticket_id, actor)
    assigned_to_name, responded_by_name = await service.resolve_staff_names([ticket])
    return ApiResponse[SupportTicketResponse].ok(
        mappers.ticket_to_response(
            ticket, service.attachment_download_url(ticket),
            assigned_to_name=assigned_to_name.get(ticket.assigned_to or ""),
            responded_by_name=responded_by_name.get(ticket.responded_by or ""),
        )
    )


@router.patch("/{ticket_id}")
async def respond_to_ticket(
    ticket_id: str, payload: RespondToTicketRequest, service: ServiceDep, actor: Annotated[User, _staff_perm("edit")]
) -> ApiResponse[SupportTicketResponse]:
    ticket = await service.respond_to_ticket(ticket_id, payload, actor)
    assigned_to_name, responded_by_name = await service.resolve_staff_names([ticket])
    return ApiResponse[SupportTicketResponse].ok(
        mappers.ticket_to_response(
            ticket, service.attachment_download_url(ticket),
            assigned_to_name=assigned_to_name.get(ticket.assigned_to or ""),
            responded_by_name=responded_by_name.get(ticket.responded_by or ""),
        )
    )
