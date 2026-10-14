"""ASGI envelope limits apply before multipart spooling, only to new voice uploads."""

import re
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.response import ApiResponse


class UploadEnvelopeTooLarge(Exception):
    pass


class VoiceUploadLimitsMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str = "/api/v1") -> None:
        self.app = app
        root = api_prefix + "/voice-assistant"
        self.limits = {
            root + "/knowledge/import": 5 * 1024 * 1024 + 65536,
            root + "/recordings/import": 20 * 1024 * 1024 + 131072,
        }
        self.active = 0
        self.audience_path = re.compile(
            re.escape(root) + r"/campaigns/[^/]+/recipients/import$"
        )

    async def reject(
        self, scope: Scope, receive: Receive, send: Send, *, status: int, message: str
    ) -> None:
        body = ApiResponse[Any].fail(code="voice_upload_rejected", message=message)
        await JSONResponse(body.model_dump(mode="json"), status_code=status)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self.limits.get(scope.get("path", ""))
        if self.audience_path.fullmatch(scope.get("path", "")):
            limit = 5 * 1024 * 1024 + 65536
        if scope["type"] != "http" or scope.get("method") != "POST" or limit is None:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length < 0 or length > limit:
            await self.reject(
                scope,
                receive,
                send,
                status=413,
                message="Voice upload request exceeds the supported size.",
            )
            return
        if self.active >= 2:
            await self.reject(
                scope,
                receive,
                send,
                status=429,
                message="Voice upload capacity is busy. Retry shortly with the same import key.",
            )
            return
        # No await between admission check and increment: one event loop per ASGI process.
        self.active += 1
        received = 0
        started = False

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise UploadEnvelopeTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if received > limit:
                return  # Multipart parsers may wrap receive failures; emit a safe 413 below.
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
            if received > limit and not started:
                await self.reject(
                    scope,
                    receive,
                    send,
                    status=413,
                    message="Voice upload exceeds the supported size; no artifact was accepted.",
                )
        except UploadEnvelopeTooLarge:
            if started:
                raise
            await self.reject(
                scope,
                receive,
                send,
                status=413,
                message="Voice upload exceeds the supported size; no artifact was accepted.",
            )
        finally:
            self.active -= 1
