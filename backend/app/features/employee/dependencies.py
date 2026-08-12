"""Employee-module auth dependencies. Reuses Auth's existing, frozen
`get_current_active_user` — no changes to any app.features.auth file. This module has no
permission engine (Module 3 territory); authorization here is a plain role check.
"""

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
from app.features.employee.service import EmployeeService

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


def get_employee_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> EmployeeService:
    return EmployeeService(db, redis)


def require_owner(current_user: CurrentUserDep) -> User:
    if current_user.role != OWNER:
        raise ForbiddenError("This action is restricted to the Owner.")
    return current_user
