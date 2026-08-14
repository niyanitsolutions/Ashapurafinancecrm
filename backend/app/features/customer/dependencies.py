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

# `require_staff` stays as a plain role check for routes that don't need a fine-grained
# permission gate. As of the Employee Permission Matrix redesign, the Customer list/
# detail/document-verify/document-reject routes in router.py use a new
# `require_permission("customer", "customers", action)` gate instead (see
# CustomerViewDep/CustomerEditDep there) — additive in front of, not a replacement for,
# the assignment-scoped visibility in customer/service.py, which is unchanged: an
# Employee still only ever sees their own assigned records regardless of grant. This
# revises decision #050's original "no require_permission here" call for those specific
# routes only; `require_staff` itself is untouched and still used elsewhere.


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
