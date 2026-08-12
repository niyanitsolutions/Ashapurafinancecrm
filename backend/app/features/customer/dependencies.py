"""Customer module dependencies. Reuses Auth's `get_current_active_user` directly (no
frozen Auth file touched). `require_customer` is a plain role check, the same pattern as
Module 2's `require_owner` — Customer self-service routes don't need PermissionEngine
(a Customer only ever acts on their own data, there's no delegation concept for them)."""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.constants.roles import CUSTOMER, EMPLOYEE, OWNER
from app.core.exceptions import ForbiddenError
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.customer.service import CustomerService
from app.features.employee.dependencies import require_owner

__all__ = [
    "CurrentUserDep",
    "get_customer_service",
    "require_customer",
    "require_owner",
    "require_staff",
]

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]

# 6B deliberately does NOT use Access Control's `require_permission` for staff
# visibility: the brief frames Employee access as inherent, assignment-scoped
# visibility ("View Assigned Customers/Applications"), not a delegable grant — an
# Employee's view is hard-scoped to their own assignments in the service layer
# regardless of any permission grant, so a require_permission gate here would add
# ceremony without adding real flexibility. See docs/decisions/DECISIONS.md #050.


def get_customer_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> CustomerService:
    return CustomerService(db, redis)


def require_customer(current_user: CurrentUserDep) -> User:
    if current_user.role != CUSTOMER:
        raise ForbiddenError("This action is restricted to Customers.")
    return current_user


def require_staff(current_user: CurrentUserDep) -> User:
    if current_user.role not in (OWNER, EMPLOYEE):
        raise ForbiddenError("This action is restricted to Owner/Employee.")
    return current_user
