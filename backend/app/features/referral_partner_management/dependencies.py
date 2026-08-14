"""Module 7 dependencies. Commission Rules and Commission Ledger/Settlement stay
`require_owner`-gated only — no Employee role for those, unlike 6C/6D which explicitly
named Employee as a delegable actor. Referral Partner self-service reuses the same
`require_customer`-style plain role check.

As of the Employee Permission Matrix redesign, partner list/detail/create gained a real
`require_permission("referral_partner_management", "partners", action)` gate
(`_perm()` in router.py) alongside the existing `require_owner` routes — additive only:
`PermissionEngine.has_permission` unconditionally passes Owner before any grant lookup,
so Owner's behavior is unchanged; an Employee whose role has been granted
view/create on `referral_partner_management:partners` gets a first-ever access path
into this module. `approve`/`deactivate` (lifecycle actions) and all Commission routes
remain `require_owner`-only, unchanged."""

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.database import get_database
from app.config.redis import get_redis
from app.constants.roles import REFERRAL_PARTNER
from app.core.exceptions import ForbiddenError
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.employee.dependencies import require_owner
from app.features.referral_partner_management.service import ReferralPartnerManagementService

__all__ = ["CurrentUserDep", "get_referral_partner_management_service", "require_owner", "require_referral_partner"]

CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


def get_referral_partner_management_service(
    db: Annotated[AsyncIOMotorDatabase[Any], Depends(get_database)], redis: Annotated[Redis, Depends(get_redis)]
) -> ReferralPartnerManagementService:
    return ReferralPartnerManagementService(db, redis)


def require_referral_partner(current_user: CurrentUserDep) -> User:
    if current_user.role != REFERRAL_PARTNER:
        raise ForbiddenError("This action is restricted to Referral Partners.")
    return current_user
