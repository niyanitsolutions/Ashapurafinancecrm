from typing import Annotated, Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.database import get_database
from app.core.response import ApiResponse
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.voice_assistant.self_hosted_health import SelfHostedHealthService
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/voice-assistant/self-hosted", tags=["voice-self-hosted"])
Owner = Annotated[User, Depends(require_owner)]


def service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> SelfHostedHealthService:
    return SelfHostedHealthService(db)


Service = Annotated[SelfHostedHealthService, Depends(service)]


@router.get("/status")
async def status(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.status(actor))


@router.post("/tests/text", dependencies=[rate_limited(5)])
async def test_text(svc: Service, actor: Owner) -> ApiResponse[Any]:
    return ApiResponse.ok(await svc.test(actor))
