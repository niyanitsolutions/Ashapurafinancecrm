"""Owner first-run registration business logic. Reuses, unmodified: Auth's `User` model/
`UserRepository`/`AuthService.issue_session`, `hash_password`, and System Settings'
`CompanySettingsRepository` — see docs/decisions/DECISIONS.md for why this coexists with
(rather than replaces) the env-var bootstrap seed script (`scripts/seed.py`).
"""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.constants.roles import OWNER
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.features.auth.constants import LoginMethod
from app.features.auth.models import ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_DISABLED, User
from app.features.auth.repository import UserRepository
from app.features.auth.schemas import LoginResponse
from app.features.auth.service import AuthService, RequestContext
from app.features.owner.constants import AuditEvent, OwnerAccountStatus, OwnerType
from app.features.owner.models import OwnerProfile
from app.features.owner.repository import OwnerProfileRepository
from app.features.owner.schemas import (
    CreateSecondaryOwnerRequest,
    RegisterOwnerRequest,
    UpdateSecondaryOwnerRequest,
)
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
        # "Does the first-run registration screen still need to run?" — gated on a
        # Primary Owner existing, not merely any role=owner user, now that Secondary
        # Owners (also role=owner) can exist too.
        return await self._owner_profiles.find_primary() is not None

    async def register_owner(self, payload: RegisterOwnerRequest, ctx: RequestContext) -> LoginResponse:
        if not payload.accept_terms:
            raise ValidationError("You must accept the Terms & Conditions.")
        if await self._owner_profiles.find_primary() is not None:
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
            OwnerProfile(
                user_id=user_id, full_name=payload.owner_name, mobile=payload.mobile, email=payload.email,
                owner_type=OwnerType.PRIMARY,
            )
        )

        settings = await self._company_settings.get_or_create()
        await self._company_settings.update(settings.require_id(), {"company_name": payload.company_name}, updated_by=user_id)

        await write_audit_log(self._db, event_type=AuditEvent.OWNER_REGISTERED, user_id=user_id, mobile=payload.mobile)

        return await self._auth.issue_session(user=user, ctx=ctx, login_method=LoginMethod.PASSWORD)

    # ---------------------------------------------------------------- owner account management

    async def get_own_account(self, user: User) -> OwnerProfile:
        profile = await self._owner_profiles.find_by_user_id(user.require_id())
        if profile is not None:
            return profile
        if user.role != OWNER:
            raise NotFoundError("Owner profile not found.")
        # An owner-role `users` row with no matching owner_profiles document can only be
        # a legacy Owner provisioned before Owner Account Management existed (e.g. via
        # the old bootstrap script, which used to insert directly into `users` — see
        # scripts/seed.py). Grandfathered in as Primary, consistent with
        # require_primary_owner's own treatment of this case (see owner/dependencies.py)
        # — never silently lock out or misclassify the legitimate sole pre-existing
        # Owner. Synthesized for display only, never persisted.
        return OwnerProfile(
            id=user.require_id(), user_id=user.require_id(), full_name="Owner", mobile=user.mobile, email="",
            owner_type=OwnerType.PRIMARY, status=user.status, created_at=user.created_at, updated_at=user.updated_at,
        )

    async def list_owner_accounts(self) -> list[OwnerProfile]:
        return await self._owner_profiles.list_all()

    async def get_owner_account(self, owner_profile_id: str) -> OwnerProfile:
        profile = await self._owner_profiles.find_by_id(owner_profile_id)
        if profile is None:
            raise NotFoundError("Owner account not found.")
        return profile

    async def create_secondary_owner(self, payload: CreateSecondaryOwnerRequest, primary_owner: User) -> OwnerProfile:
        if await self._users.find_by_mobile(payload.mobile) is not None:
            raise ConflictError("This mobile number is already registered.")
        if await self._owner_profiles.find_by_email(payload.email) is not None:
            raise ConflictError("This email is already registered.")

        # Owner sets the initial password directly (no OTP invite exists for the Owner
        # role) — same trust decision already made for Owner-created Employees (decision
        # #017). must_change_password forces the Secondary Owner to set their own
        # password on first login.
        user = User(
            mobile=payload.mobile, role=OWNER, status=ACCOUNT_STATUS_ACTIVE,
            password_hash=hash_password(payload.initial_password), is_mobile_verified=True,
            must_change_password=True, created_by=primary_owner.require_id(),
        )
        user_id = await self._users.insert(user)

        # owner_type is always stamped SECONDARY here, never taken from the request
        # payload — CreateSecondaryOwnerRequest has no such field, closing off a
        # privilege-escalation attempt at the schema level, not just in this line.
        profile = OwnerProfile(
            user_id=user_id, full_name=payload.full_name, mobile=payload.mobile, email=payload.email,
            owner_type=OwnerType.SECONDARY, created_by=primary_owner.require_id(),
        )
        profile_id = await self._owner_profiles.insert(profile)

        await write_audit_log(
            self._db, event_type=AuditEvent.SECONDARY_OWNER_CREATED, user_id=primary_owner.require_id(),
            metadata={"owner_profile_id": profile_id, "created_user_id": user_id},
        )
        return await self._owner_profiles.find_by_id(profile_id) or profile

    async def update_secondary_owner(
        self, owner_profile_id: str, payload: UpdateSecondaryOwnerRequest, primary_owner: User
    ) -> OwnerProfile:
        profile = await self._get_secondary_or_403(owner_profile_id)
        updates: dict[str, Any] = {}

        if payload.email is not None and payload.email != profile.email:
            if await self._owner_profiles.find_by_email(payload.email, exclude_id=owner_profile_id) is not None:
                raise ConflictError("This email is already registered.")
            updates["email"] = payload.email
        if payload.full_name is not None:
            updates["full_name"] = payload.full_name

        if not updates:
            return profile

        updated = await self._owner_profiles.update(owner_profile_id, updates, updated_by=primary_owner.require_id())
        await write_audit_log(
            self._db, event_type=AuditEvent.SECONDARY_OWNER_UPDATED, user_id=primary_owner.require_id(),
            metadata={"owner_profile_id": owner_profile_id, "fields": list(updates.keys())},
        )
        return updated or profile

    async def deactivate_secondary_owner(self, owner_profile_id: str, primary_owner: User) -> OwnerProfile:
        profile = await self._get_secondary_or_403(owner_profile_id)
        # Pairs profile status with login access — same pattern as Employee deactivation
        # (employee/service.py::_sync_login_status): the account row is never deleted.
        await self._users.update(profile.user_id, {"status": ACCOUNT_STATUS_DISABLED})
        updated = await self._owner_profiles.update(
            owner_profile_id, {"status": OwnerAccountStatus.INACTIVE}, updated_by=primary_owner.require_id()
        )
        await write_audit_log(
            self._db, event_type=AuditEvent.SECONDARY_OWNER_DEACTIVATED, user_id=primary_owner.require_id(),
            metadata={"owner_profile_id": owner_profile_id},
        )
        return updated or profile

    async def activate_secondary_owner(self, owner_profile_id: str, primary_owner: User) -> OwnerProfile:
        profile = await self._get_secondary_or_403(owner_profile_id)
        await self._users.update(profile.user_id, {"status": ACCOUNT_STATUS_ACTIVE})
        updated = await self._owner_profiles.update(
            owner_profile_id, {"status": OwnerAccountStatus.ACTIVE}, updated_by=primary_owner.require_id()
        )
        await write_audit_log(
            self._db, event_type=AuditEvent.SECONDARY_OWNER_ACTIVATED, user_id=primary_owner.require_id(),
            metadata={"owner_profile_id": owner_profile_id},
        )
        return updated or profile

    async def _get_secondary_or_403(self, owner_profile_id: str) -> OwnerProfile:
        profile = await self._owner_profiles.find_by_id(owner_profile_id)
        if profile is None:
            raise NotFoundError("Owner account not found.")
        if profile.owner_type == OwnerType.PRIMARY:
            # Backend-enforced, not just hidden in the UI — the Primary Owner can never
            # be edited/deactivated/activated through this Secondary-Owner-only action,
            # even by itself (see require_primary_owner — only the Primary Owner can
            # even reach this far, and it still refuses to target itself here).
            raise ForbiddenError("The Primary Owner cannot be modified through this action.")
        return profile
