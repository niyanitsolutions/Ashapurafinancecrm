from datetime import datetime

from pydantic import BaseModel, Field

from app.features.support.constants import IssueType, Priority


class CreateSupportTicketRequest(BaseModel):
    issue_type: str = Field(pattern=f"^({'|'.join(IssueType.ALL)})$")
    priority: str = Field(pattern=f"^({'|'.join(Priority.ALL)})$")
    subject: str = Field(min_length=1)
    message: str = Field(min_length=1)
    attachment_s3_key: str | None = None


class SupportTicketResponse(BaseModel):
    id: str
    ticket_code: str
    issue_type: str
    priority: str
    subject: str
    message: str
    attachment_download_url: str | None
    assigned_to: str | None
    assigned_to_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AttachmentUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str | None = None


class AttachmentUploadUrlResponse(BaseModel):
    upload_url: str
    s3_key: str
