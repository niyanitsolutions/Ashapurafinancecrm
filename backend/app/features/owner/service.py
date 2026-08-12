"""Owner first-run registration business logic. Reuses, unmodified: Auth's `User` model/
`UserRepository`/`AuthService.issue_session`, `hash_password`, and System Settings'
`CompanySettingsRepository` — see docs/decisions/DECISIONS.md for why this coexists with
(rather than replaces) the env-var bootstrap seed script (`scripts/seed.py`).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ValidationError
from app.features.auth.constants import LoginMethod
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, User
from app.features.auth.repository import UserRepository
from app.features.auth.schemas import LoginResponse
from app.features.auth.service import AuthService, RequestContext
from app.features.owner.constants import AuditEvent
from app.features.owner.models import OwnerProfile
from app.features.owner.repository import OwnerProfileRepository
from app.features.owner.schemas import RegisterOwnerRequest
from app.features.system_settings.repository import CompanySettingsRepository
from app.security.password import hash_password
from app.shared.audit_log import write_audit_log


class OwnerService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._owner_profiles = OwnerProfileRepository(db)
        self._company_settings = CompanySettingsRepository(db)
        self._auth = AuthService(db, redis)

    async def registration_status(self) -> bool:
        return await self._users.count({"role": OWNER}) > 0

    async def register_owner(self, payload: RegisterOwnerRequest, ctx: RequestContext) -> LoginResponse:
        if not payload.accept_terms:
            raise ValidationError("You must accept the Terms & Conditions.")
        if await self._users.count({"role": OWNER}) > 0:
            raise ConflictError("An Owner account already exists. Please sign in.")
        if await self._users.find_by_mobile(payload.mobile) is not None:
            raise ConflictError("This mobile number is already registered.")

        # Self-registered, not OTP-verified — direct-password creation, the same trust
        # decision already made for Owner-created Employees (see employee/service.py).
        user = User(
            mobile=payload.mobile, role=OWNER, status=ACCOUNT_STATUS_ACTIVE,
            password_hash=hash_password(payload.password), is_mobile_verified=False,
        )
        user_id = await self._users.insert(user)
        user = await self._users.find_by_id(user_id)
        assert user is not None

        await self._owner_profiles.insert(
            OwnerProfile(user_id=user_id, full_name=payload.owner_name, mobile=payload.mobile, email=payload.email)
        )

        settings = await self._company_settings.get_or_create()
        await self._company_settings.update(settings.require_id(), {"company_name": payload.company_name}, updated_by=user_id)

        await write_audit_log(self._db, event_type=AuditEvent.OWNER_REGISTERED, user_id=user_id, mobile=payload.mobile)

        return await self._auth.issue_session(user=user, ctx=ctx, login_method=LoginMethod.PASSWORD)
