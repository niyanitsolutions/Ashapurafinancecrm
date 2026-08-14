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
    # WhatsApp + MSG91 only — see models.py:CommunicationTemplate's own docstring.
    provider_template_name: str | None = None
    provider_template_namespace: str | None = None
    provider_template_language: str | None = None


class UpdateTemplateRequest(BaseModel):
    name: str | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None
    language: str | None = None
    provider_template_name: str | None = None
    provider_template_namespace: str | None = None
    provider_template_language: str | None = None


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
    provider_template_name: str | None
    provider_template_namespace: str | None
    provider_template_language: str | None
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


# ---------------------------------------------------------------------- Stage 3: CRM record messaging


class SendMessageRequest(BaseModel):
    entity_type: str = Field(pattern="^(lead|customer)$")
    entity_id: str
    channel: str = Field(pattern=f"^({'|'.join(Channel.ALL)})$")
    template_id: str
    # Extra template variables beyond the ones this endpoint always resolves itself
    # (customer_name/mobile/email, from the Lead/Customer record) — e.g. a free-text
    # {{secure_link}} for a template that references it. Never lets the caller override
    # the recipient address itself (always server-resolved — see
    # CommunicationService.send_crm_message's own docstring).
    variables: dict[str, str] = Field(default_factory=dict)


class SendMessageResponse(BaseModel):
    success: bool
    queue_item_id: str | None
    status: str | None
    error: str | None


# ---------------------------------------------------------------------- Stage 3: Bulk Messaging


class CreateBulkMessageJobRequest(BaseModel):
    channel: str = Field(pattern=f"^({'|'.join(Channel.ALL)})$")
    template_id: str
    recipient_type: str = Field(pattern="^(lead|customer)$")
    recipient_ids: list[str] = Field(min_length=1, max_length=10000)


class BulkMessageJobResponse(BaseModel):
    id: str
    channel: str
    template_id: str
    recipient_type: str
    recipient_count: int
    queued_count: int
    skipped_count: int
    status: str
    created_at: datetime
    # Live counts computed from the queue/history at read time — not stored on the job
    # itself, so they're always current even mid-processing.
    pending: int
    sent: int
    delivered: int
    failed: int


class BulkMessageJobListResponse(BaseModel):
    id: str
    channel: str
    template_id: str
    recipient_type: str
    recipient_count: int
    queued_count: int
    skipped_count: int
    status: str
    created_at: datetime
