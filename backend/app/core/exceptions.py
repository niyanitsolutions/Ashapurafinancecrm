"""Domain exceptions and their mapping to the standard error envelope. Features raise
these instead of HTTPException directly, so the error taxonomy (docs/api/ERROR_CODES.md)
stays centralized and consistent across every route.
"""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.response import ApiResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    code = "internal_error"
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: object | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    code = "not_found"
    http_status = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    code = "validation_error"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class UnauthorizedError(AppError):
    code = "unauthorized"
    http_status = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = status.HTTP_403_FORBIDDEN


class ConflictError(AppError):
    code = "conflict"
    http_status = status.HTTP_409_CONFLICT


class RateLimitedError(AppError):
    code = "rate_limited"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # registered only for AppError, see main.py
    body = ApiResponse[None].fail(code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump(mode="json"))


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """FastAPI's own request-body/query/path validation (Pydantic `Field(pattern=...)`,
    missing required fields, etc.) raises `RequestValidationError` *before* a route
    handler ever runs, so it never goes through `AppError`/`app_error_handler` — without
    this, it falls through to FastAPI's default handler and leaks its raw
    `{"detail": [...]}` shape (including regex patterns in `ctx`) instead of the app's
    envelope. `code` is deliberately the same `"validation_error"` the app's own
    `ValidationError` already uses, so the frontend has exactly one code to branch on;
    `details` carries a compact, machine-readable per-field list (never the raw `ctx`/
    pattern) that `shared/api/errors.ts` turns into business-friendly, field-specific
    copy. See docs/api/ERROR_CODES.md.
    """
    assert isinstance(exc, RequestValidationError)  # registered only for this type, see main.py
    field_errors = [
        {
            "loc": [str(part) for part in error["loc"] if part not in ("body", "query", "path")],
            "type": error["type"],
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]
    body = ApiResponse[None].fail(code="validation_error", message="Please check the highlighted fields.", details=field_errors)
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content=body.model_dump(mode="json"))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort safety net: any exception not already an `AppError` (a genuine bug,
    a third-party client error, etc.) must never leak a stack trace or internal
    implementation detail to the caller — only ever this fixed, generic message. Full
    detail (including traceback) goes to the server log for developers, never the
    response body.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    body = ApiResponse[None].fail(code="internal_error", message="An unexpected server error occurred. Please try again later.")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump(mode="json"))
