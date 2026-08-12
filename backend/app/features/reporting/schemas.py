from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class ReportColumn(BaseModel):
    key: str
    label: str


class ReportResult(BaseModel):
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    summary: dict[str, Any] | None = None


class ReportDefinitionResponse(BaseModel):
    key: str
    label: str
    category: str
    description: str


class CreateSavedFilterRequest(BaseModel):
    report_key: str
    label: str
    filters: dict[str, Any] = {}


class SavedFilterResponse(BaseModel):
    id: str
    report_key: str
    label: str
    filters: dict[str, Any]
    created_at: datetime


class CreateScheduledReportRequest(BaseModel):
    report_key: str
    label: str
    filters: dict[str, Any] = {}
    frequency: str
    recipient_user_ids: list[str] = []


class UpdateScheduledReportRequest(BaseModel):
    label: str | None = None
    filters: dict[str, Any] | None = None
    frequency: str | None = None
    recipient_user_ids: list[str] | None = None
    is_active: bool | None = None


class ScheduledReportResponse(BaseModel):
    id: str
    report_key: str
    label: str
    filters: dict[str, Any]
    frequency: str
    recipient_user_ids: list[str]
    is_active: bool
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportFilters(BaseModel):
    """The one filter every report definition accepts. A few reports also read one
    extra, report-specific query param directly (e.g. `partner_id`) — kept out of this
    shared shape since it doesn't apply universally."""

    date_from: date | None = None
    date_to: date | None = None
