from app.features.support.models import SupportTicket
from app.features.support.schemas import SupportTicketResponse


def ticket_to_response(ticket: SupportTicket, attachment_download_url: str | None) -> SupportTicketResponse:
    return SupportTicketResponse(
        id=ticket.require_id(),
        ticket_code=ticket.ticket_code,
        issue_type=ticket.issue_type,
        priority=ticket.priority,
        subject=ticket.subject,
        message=ticket.message,
        attachment_download_url=attachment_download_url,
        assigned_to=ticket.assigned_to,
        assigned_to_name=None,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )
