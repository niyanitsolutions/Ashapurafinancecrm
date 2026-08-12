from datetime import datetime

from pydantic import BaseModel, Field

from app.features.communication.constants import Channel, TemplateCategory


class CreateTemplateRequest(BaseModel):
    name: str
    channel: str = Field(pattern=f"^({'|'.join(Channel.ALL)})$")
    category: str = Field(pattern=f"^({'|'.join(TemplateCategory.ALL)})$")
    subject: str | None = None
    body: str
    language: str = "en"


class UpdateTemplateRequest(BaseModel):
    name: str | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None
    language: str | None = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    channel: str
    category: str
    subject: str | None
    body: str
    variables: list[str]
    language: str
    status: str
    created_at: datetime


class QueueItemResponse(BaseModel):
    id: str
    channel: str
    recipient: str
    template_id: str
    variables: dict[str, str]
    rendered_subject: str | None
    rendered_body: str
    status: str
    provider_message_id: str | None
    retry_count: int
    next_retry_at: datetime | None
    error_detail: str | None
    business_event: str | None
    entity_type: str | None
    entity_id: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class HistoryResponse(BaseModel):
    id: str
    queue_item_id: str
    channel: str
    provider: str
    recipient: str
    template_id: str
    template_name: str
    variables: dict[str, str]
    status: str
    error: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    retry_count: int
    created_at: datetime
