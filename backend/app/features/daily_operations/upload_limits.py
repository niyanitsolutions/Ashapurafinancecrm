"""Reject oversized envelopes before Starlette's multipart parser creates temp files."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.response import ApiResponse
from app.features.bulk_import.files import MAX_BYTES


class DailyUploadLimitsMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str = "/api/v1") -> None:
        self.app = app
        self.prefix = api_prefix + "/daily-operations/transfers/"
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not path.startswith(self.prefix)
            or not path.endswith("/preview")
        ):
            await self.app(scope, receive, send)
            return
        limit = MAX_BYTES + 65536
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        status = 413 if length < 0 or length > limit else 429 if self.active >= 2 else 0
        if status:
            await self.reject(scope, receive, send, status)
            return
        self.active += 1
        try:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    await self.reject(scope, receive, send, 413)
                    return
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, send)
        finally:
            self.active -= 1

    async def reject(self, scope: Scope, receive: Receive, send: Send, status: int) -> None:
        body = ApiResponse[None].fail(
            code="daily_upload_rejected",
            message="Upload exceeds the supported size."
            if status == 413
            else "Upload capacity is busy. Retry shortly.",
        )
        await JSONResponse(body.model_dump(mode="json"), status_code=status)(scope, receive, send)
