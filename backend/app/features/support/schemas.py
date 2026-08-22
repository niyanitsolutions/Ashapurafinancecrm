from datetime import datetime

from pydantic import BaseModel, Field

from app.features.support.constants import IssueType, Priority, TicketStatus


class CreateSupportTicketRequest(BaseModel):
    issue_type: str = Field(pattern=f"^({'|'.join(IssueType.ALL)})$")
    priority: str = Field(pattern=f"^({'|'.join(Priority.ALL)})$")
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)
    attachment_s3_key: str | None = None


class RespondToTicketRequest(BaseModel):
    """Staff respond/update-status action. `status` is optional so a staff member can
    reply without necessarily closing the ticket in the same call; when omitted the
    ticket's current status is left unchanged unless it's still OPEN (auto-advanced to
    IN_PROGRESS on first response — see SupportTicketService.respond_to_ticket)."""

    staff_response: str = Field(min_length=1)
    status: str | None = Field(default=None, pattern=f"^({'|'.join(TicketStatus.ALL)})$")


class SupportTicketResponse(BaseModel):
    id: str
    ticket_code: str
    customer_id: str
    issue_type: str
    priority: str
    subject: str
    message: str
    attachment_download_url: str | None
    assigned_to: str | None
    assigned_to_name: str | None = None
    staff_response: str | None = None
    responded_by_name: str | None = None
    responded_at: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AttachmentUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str | None = None


class AttachmentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str
