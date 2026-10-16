from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.platform_schemas import (
    ActivationChange,
    Component,
    ComponentChange,
    EmergencyChange,
    Environment,
)
from app.features.voice_assistant.platform_service import PlatformService
from app.features.voice_assistant.speech_jobs import SpeechJobs
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/platform", tags=["voice-platform"])
Owner = Annotated[User, Depends(require_owner)]
Database = Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)]


@router.get("/speech-profiles")
async def profiles(actor: Owner, db: Database) -> ApiResponse[Any]:
    return ApiResponse.ok(await SpeechJobs(db).catalog(actor))


@router.get("/{environment}")
async def state(environment: Environment, actor: Owner, db: Database) -> ApiResponse[Any]:
    return ApiResponse.ok(await PlatformService(db).status(environment, actor))


@router.put("/{environment}/components/{component}", dependencies=[rate_limited(20)])
async def component_change(
    environment: Environment,
    component: Component,
    payload: ComponentChange,
    actor: Owner,
    db: Database,
) -> ApiResponse[Any]:
    return ApiResponse.ok(
        await PlatformService(db).component(environment, component, payload, actor)
    )


@router.post("/{environment}/activation", dependencies=[rate_limited(10)])
async def activation(
    environment: Environment, payload: ActivationChange, actor: Owner, db: Database
) -> ApiResponse[Any]:
    return ApiResponse.ok(await PlatformService(db).activation(environment, payload, actor))


@router.post("/{environment}/emergency", dependencies=[rate_limited(30)])
async def emergency(
    environment: Environment, payload: EmergencyChange, actor: Owner, db: Database
) -> ApiResponse[Any]:
    return ApiResponse.ok(await PlatformService(db).emergency(environment, actor, payload.reason))


@router.post("/{environment}/speech-tests/{profile_id}", dependencies=[rate_limited(5)])
async def speech_test(
    environment: Environment,
    profile_id: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{1,64}$")],
    actor: Owner,
    db: Database,
) -> ApiResponse[Any]:
    return ApiResponse.ok(await SpeechJobs(db).submit(environment, profile_id, actor))


@router.get("/{environment}/speech-tests")
async def speech_tests(
    environment: Environment, actor: Owner, db: Database, page: int = Query(1, ge=1)
) -> ApiResponse[Any]:
    return ApiResponse.ok(await SpeechJobs(db).list(environment, actor, page))


@router.post("/{environment}/pipeline-tests", dependencies=[rate_limited(3)])
async def pipeline_test(environment: Environment, actor: Owner, db: Database) -> ApiResponse[Any]:
    return ApiResponse.ok(await SpeechJobs(db).submit(environment, "", actor, pipeline=True))


@router.get("/{environment}/speech-tests/{record_id}/audio")
async def speech_audio(
    environment: Environment, record_id: str, actor: Owner, db: Database
) -> Response:
    audio = await SpeechJobs(db).audio(environment, record_id, actor)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="local-speech-test.wav"',
            "X-Content-Type-Options": "nosniff",
        },
    )
