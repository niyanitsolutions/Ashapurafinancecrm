from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.response import ApiResponse
from app.features.access_control.permission_engine import require_permission
from app.features.auth.models import User
from app.features.voice_assistant.callback_schemas import (
    CallbackAction,
    CallbackInput,
    CallbackTimeInput,
    EntityType,
)
from app.features.voice_assistant.callback_service import CallbackService
from app.features.voice_assistant.callback_time import interpret_time
from app.features.voice_assistant.platform_schemas import Environment
from app.middleware.rate_limit import rate_limited
from app.utils.datetime import utc_now

router = APIRouter(prefix="/voice-assistant/callbacks", tags=["voice-callbacks"])
View = Annotated[User, require_permission("voice_assistant", "calls", "view")]
Create = Annotated[User, require_permission("voice_assistant", "calls", "create")]
Edit = Annotated[User, require_permission("voice_assistant", "calls", "edit")]
Database = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]


@router.post("/interpret-time", dependencies=[rate_limited(10)])
async def callback_time(payload: CallbackTimeInput, actor: Create) -> ApiResponse[Any]:
    return ApiResponse.ok(interpret_time(payload.request, payload.timezone, utc_now()))


@router.get("")
async def callbacks(
    entity_type: EntityType,
    entity_id: Annotated[str, Query(pattern=r"^[a-f0-9]{24}$")],
    db: Database,
    actor: View,
    environment: Environment = "test",
    page: int = Query(1, ge=1),
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await CallbackService(db).list(entity_type, entity_id, environment, actor, page)
    )


@router.post("", dependencies=[rate_limited(10)])
async def create_callback(payload: CallbackInput, db: Database, actor: Create) -> ApiResponse[Any]:
    return ApiResponse.ok(await CallbackService(db).create(payload, actor))


@router.post("/{record_id}/actions", dependencies=[rate_limited(20)])
async def callback_action(
    record_id: str, payload: CallbackAction, db: Database, actor: Edit
) -> ApiResponse[Any]:
    return ApiResponse.ok(await CallbackService(db).action(record_id, payload, actor))


@router.get("/{record_id}/history")
async def callback_history(
    record_id: str, db: Database, actor: View, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await CallbackService(db).history(record_id, actor, page))


@router.post("/{record_id}/resolve-owner", dependencies=[rate_limited(20)])
async def callback_owner_resolution(record_id: str, payload: CallbackAction, db: Database, actor: Edit) -> ApiResponse[Any]:
    return ApiResponse.ok(await CallbackService(db).resolve_owner(record_id, payload, actor))
