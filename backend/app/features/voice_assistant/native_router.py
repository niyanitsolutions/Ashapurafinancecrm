from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.native_config import NativeConnectionInput
from app.features.voice_assistant.native_service import NativeVoiceService
from app.features.voice_assistant.number_schemas import TelephoneNumberAction, TelephoneNumberInput
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/native", tags=["voice-native"])
Owner = Annotated[User, Depends(require_owner)]


def service(db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]) -> NativeVoiceService:
    return NativeVoiceService(db)


Service = Annotated[NativeVoiceService, Depends(service)]


@router.get("/connections")
async def connections(svc: Service, actor: Owner, page: int = Query(1, ge=1)) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.connections(actor, page))


@router.post("/connections", dependencies=[rate_limited(10)])
async def add_connection(
    payload: NativeConnectionInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_connection(payload, actor))


@router.put("/connections/{record_id}")
async def edit_connection(
    record_id: str, payload: NativeConnectionInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_connection(payload, actor, record_id))


@router.post("/connections/{record_id}/test", dependencies=[rate_limited(5)])
async def test_connection(record_id: str, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.test_connection(record_id, actor))


@router.get("/connections/{record_id}/events")
async def connection_events(
    record_id: str, svc: Service, actor: Owner, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.connection_events(record_id, actor, page))


@router.get("/numbers")
async def numbers(svc: Service, actor: Owner, page: int = Query(1, ge=1)) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.numbers(actor, page))


@router.post("/numbers", dependencies=[rate_limited(10)])
async def add_number(payload: TelephoneNumberInput, svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_number(payload, actor))


@router.put("/numbers/{record_id}")
async def edit_number(
    record_id: str, payload: TelephoneNumberInput, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.save_number(payload, actor, record_id))


@router.post("/numbers/{record_id}/actions")
async def number_action(
    record_id: str, payload: TelephoneNumberAction, svc: Service, actor: Owner
) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.number_action(record_id, payload, actor))
