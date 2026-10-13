from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.shared.base_document import BaseDocument

CallState = Literal[
    "queued",
    "ringing",
    "ai_active",
    "human_active",
    "transferring",
    "completed",
    "missed",
    "failed",
    "cancelled",
]
TERMINAL = {"completed", "missed", "failed", "cancelled"}
TRANSITIONS = {
    "queued": {"ringing", "cancelled", "failed"},
    "ringing": {"human_active", "ai_active", "missed", "completed", "failed"},
    "ai_active": {"transferring", "completed", "failed"},
    "human_active": {"completed", "failed"},
    "transferring": {"human_active", "ai_active", "completed", "failed"},
}


class CallSession(BaseDocument):
    status: CallState = "ringing"
    provider: Literal["mock"] = "mock"
    direction: Literal["incoming", "outgoing"]
    contact_label: str
    idempotency_key: str
    owner_user_id: str
    assigned_employee_id: str | None = None
    language: str = "en"
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    deadline_at: datetime
    duration_seconds: int = 0
    recording_status: Literal["disabled"] = "disabled"
    transfer_outcome: str | None = None
    consent_reference: str | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeArticle(BaseDocument):
    title: str
    content: str
    language: str = "en"
    status: Literal["draft", "review", "published", "archived"] = "draft"
    content_hash: str
    chunks: list[str]
    effective_on: str | None = None
    expires_on: str | None = None
    reviewed_by: str | None = None
    revisions: list[dict[str, Any]] = Field(default_factory=list)
