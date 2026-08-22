from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    body: str = Field(min_length=1)


class ConversationMessageResponse(BaseModel):
    id: str
    sender_role: str
    sender_name: str
    body: str
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    customer_id: str
    customer_name: str | None = None
    employee_id: str | None
    employee_name: str | None = None
    last_message_at: datetime
    last_message_preview: str
    messages: list[ConversationMessageResponse] = Field(default_factory=list)
