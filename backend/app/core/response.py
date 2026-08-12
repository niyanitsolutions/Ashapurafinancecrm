"""Standard API envelope. Every /api/v1 route returns this shape so frontend/mobile
clients have exactly one response contract to parse (see docs/api/API_STANDARDS.md).
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ResponseMeta(BaseModel):
    pagination: PaginationMeta | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta | None = None

    @classmethod
    def ok(cls, data: T | None = None, meta: ResponseMeta | None = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str, details: Any | None = None) -> "ApiResponse[T]":
        return cls(success=False, error=ErrorDetail(code=code, message=message, details=details))
