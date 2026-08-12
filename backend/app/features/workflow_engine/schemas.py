"""Request/response shapes shared by both `loan_management` and `insurance_management`
routers — assignment, document requests, notes, and the merged status+note Timeline are
identical in shape across both pipelines; only the case-type-specific decision/action
schemas live in each product module's own `schemas.py`.
"""

from datetime import datetime

from pydantic import BaseModel


class AssignCaseRequest(BaseModel):
    employee_id: str


class RequestDocumentsRequest(BaseModel):
    document_type_ids: list[str]


class AddCaseNoteRequest(BaseModel):
    text: str


class HoldCaseRequest(BaseModel):
    reason: str  # HoldReason.ALL
    remarks: str | None = None


class CaseNoteResponse(BaseModel):
    id: str
    text: str
    created_by: str | None
    created_at: datetime


class CaseTimelineEntryResponse(BaseModel):
    type: str  # "status" | "note"
    from_status: str | None = None
    to_status: str | None = None
    remarks: str | None = None
    text: str | None = None
    created_by: str | None
    created_at: datetime
