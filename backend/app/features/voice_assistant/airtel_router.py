from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.exceptions import ForbiddenError
from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.airtel_config import AirtelConnectionInput
from app.features.voice_assistant.airtel_service import AirtelVoiceService
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/airtel", tags=["voice-airtel"])
Owner = Annotated[User, Depends(require_owner)]


def service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> AirtelVoiceService:
    return AirtelVoiceService(db)


Service = Annotated[AirtelVoiceService, Depends(service)]


@router.get("/connection")
async def status(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.status(actor))


@router.put("/connection", dependencies=[rate_limited(10)])
async def save(payload: AirtelConnectionInput, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save(payload, actor))


@router.post("/tests/local", dependencies=[rate_limited(5)])
async def validate(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.validate(actor))


@router.post("/webhooks/events")
@router.post("/webhooks/cdr")
async def blocked_callback() -> None:
    # Do not ingest unauthenticated financial/call data or acknowledge processing.
    raise ForbiddenError(
        "Airtel callback ingestion is disabled pending the agreed authentication and correlation contract."
    )


@router.websocket("/media")
async def blocked_media(websocket: WebSocket) -> None:
    await websocket.close(code=1013, reason="Airtel live media is not verified or enabled.")
