from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.constants.roles import OWNER
from app.core.exceptions import ForbiddenError
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.owner.constants import OwnerType
from app.features.owner.repository import OwnerProfileRepository
from app.features.owner.service import OwnerService

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


def get_owner_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> OwnerService:
    return OwnerService(db, redis)


async def require_primary_owner(
    current_user: CurrentUserDep,
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
) -> User:
    """Owner Account Management (create/edit/deactivate/activate a Secondary Owner) is
    restricted to the Primary Owner only. Always re-checked against the database rather
    than any client-supplied claim — same convention as every other role/permission
    dependency in the app (see access_control.permission_engine) — so a Secondary Owner
    can never reach these actions even via a hand-crafted request."""
    if current_user.role != OWNER:
        raise ForbiddenError("This action is restricted to the Primary Owner.")
    profile = await OwnerProfileRepository(db).find_by_user_id(current_user.require_id())
    # No matching owner_profiles row can only mean a legacy Owner provisioned before
    # Owner Account Management existed (back when at most one Owner could ever exist) —
    # grandfathered in as Primary rather than locked out (see OwnerService.get_own_account
    # for the matching read-side treatment). Only an explicit owner_type="secondary" row
    # is ever rejected here.
    if profile is not None and profile.owner_type != OwnerType.PRIMARY:
        raise ForbiddenError("This action is restricted to the Primary Owner.")
    return current_user
