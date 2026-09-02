from datetime import datetime

from pydantic import BaseModel, Field


class BulkDeleteRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)


class BinEntryResponse(BaseModel):
    id: str
    resource_key: str
    module_label: str
    stage_label: str | None
    record_code: str | None
    record_summary: str | None
    document_id: str
    deleted_by: str
    deleted_by_name: str | None
    deleted_at: datetime
    purge_at: datetime


class BulkDeleteResponse(BaseModel):
    deleted: list[str]
    skipped: list[dict[str, str]]


class DeletableResourceResponse(BaseModel):
    key: str
    module_label: str
