from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.features.owner.service import OwnerService


def get_owner_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> OwnerService:
    return OwnerService(db, redis)
