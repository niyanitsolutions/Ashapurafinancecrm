from typing import Any

from fastapi import APIRouter

from app.config.database import ping as ping_mongo
from app.config.redis import get_redis
from app.core.response import ApiResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> ApiResponse[dict[str, Any]]:
    mongo_ok = await ping_mongo()
    redis_ok = bool(await get_redis().ping())
    return ApiResponse[dict[str, Any]].ok(
        data={"mongo": mongo_ok, "redis": redis_ok, "status": "ok" if mongo_ok and redis_ok else "degraded"}
    )
