from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, WebSocket
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.smartflo_config import (
    SmartfloConnectionInput,
    SmartfloWebhookInput,
)
from app.features.voice_assistant.smartflo_media import offline_audio_test
from app.features.voice_assistant.smartflo_service import SmartfloService
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/smartflo", tags=["voice-assistant-smartflo"])
Owner = Annotated[User, Depends(require_owner)]


def service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> SmartfloService:
    return SmartfloService(db)


Service = Annotated[SmartfloService, Depends(service)]


@router.get("/connection")
async def connection(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.status())


@router.put("/connection")
async def save_connection(
    payload: SmartfloConnectionInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save(payload, actor))


@router.post("/tests/connection", dependencies=[rate_limited(5)])
async def test_connection(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.test_connection(actor))


@router.post("/tests/webhook", dependencies=[rate_limited(10)])
async def test_webhook(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.test_webhook(actor))


@router.post("/tests/audio", dependencies=[rate_limited(10)])
async def test_audio(svc: Service, actor: Owner) -> ApiResponse[Any]:
    await svc.audit(actor, "offline_audio_test")
    return ApiResponse.ok(offline_audio_test())


@router.get("/events")
async def events(svc: Service, actor: Owner, page: int = Query(1, ge=1)) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.events(page))


@router.post("/webhooks/{channel}", dependencies=[rate_limited(120)])
async def webhook(
    channel: Literal["incoming", "answered", "hangup"],
    request: Request,
    svc: Service,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiResponse[Any]:
    await svc.authenticate_callback(authorization)
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise ValidationError("Configure JSON POST callbacks in Smartflo.")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > 16384:
            raise ValidationError("Webhook payload exceeds the configured limit.")
    try:
        payload = SmartfloWebhookInput.model_validate_json(body)
    except ValueError as exc:
        raise ValidationError(
            "Callback payload must match the documented CRM mapping and UTC ISO timestamp format."
        ) from exc
    return ApiResponse.ok(await svc.ingest(channel, payload))


@router.post("/stream/resolve")
async def resolve(svc: Service, authorization: Annotated[str | None, Header()] = None) -> None:
    await svc.authenticate_callback(authorization)
    raise ForbiddenError(
        "Dynamic audio resolution is blocked until sandbox access and streaming speech adapters are verified. Do not register this resolver yet."
    )


@router.websocket("/media")
async def media(websocket: WebSocket) -> None:
    # Do not accept real audio or mint stream sessions with no validated speech engine.
    await websocket.close(code=1013, reason="Smartflo live audio is not verified or enabled.")
