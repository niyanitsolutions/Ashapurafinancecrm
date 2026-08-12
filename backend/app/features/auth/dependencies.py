from typing import Annotated, Any

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.core.exceptions import UnauthorizedError
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.auth.service import AuthService, RequestContext
from app.middleware.auth import get_current_subject


def get_auth_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AuthService:
    return AuthService(db, redis)


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


async def get_current_active_user(
    subject: Annotated[str, Depends(get_current_subject)],
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> User:
    user = await UserRepository(db).find_by_id(subject)
    if user is None or user.status != ACCOUNT_STATUS_ACTIVE:
        raise UnauthorizedError("Account is not active.")
    return user
