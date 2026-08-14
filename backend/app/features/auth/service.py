"""Authentication business logic. Router stays thin (HTTP concerns only); every rule
described in docs/AUTHENTICATION.md lives here.
"""

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.config.security import get_security_policy
from app.config.settings import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.features.auth import lockout_service, otp_service
from app.features.auth.constants import (
    INVITABLE_ROLES,
    INVITER_ROLES_BY_INVITEE_ROLE,
    AuditEvent,
    LoginMethod,
    OtpPurpose,
)
from app.features.auth.exceptions import (
    AccountLockedError,
    AlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidRoleForSignupError,
    InvalidTicketError,
)
from app.features.auth.models import (
    ACCOUNT_STATUS_ACTIVE,
    ACCOUNT_STATUS_PENDING_PASSWORD,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_LOGGED_OUT,
    SESSION_STATUS_ROTATED,
    Session,
    User,
)
from app.features.auth.repository import SessionRepository, UserRepository
from app.features.auth.schemas import LoginResponse, ProfileResponse, TokenPairResponse
from app.features.employee.repository import EmployeeRepository
from app.features.owner.repository import OwnerProfileRepository
from app.security.hashing import hash_value
from app.security.jwt import (
    TokenError,
    TokenType,
    create_access_token,
    create_otp_verified_token,
    create_refresh_token,
    decode_token,
)
from app.security.password import hash_password, verify_password
from app.services.geoip.client import GeoLocation, NotConfiguredGeoIpClient
from app.services.sms.client import NotConfiguredSmsClient
from app.shared.audit_log import write_audit_log
from app.utils.datetime import utc_now
from app.utils.user_agent import parse_user_agent


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None
    user_agent: str | None


_USED_TICKET_KEY_PREFIX = "used_otp_ticket"

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase[Any], redis: Redis) -> None:
        self._db = db
        self._redis = redis
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)
        self._owner_profiles = OwnerProfileRepository(db)
        self._employees = EmployeeRepository(db)

    # ---------------------------------------------------------------- signup / OTP

    async def send_otp(self, *, mobile: str, role: str, inviter: User) -> str | None:
        """Issues a signup OTP for a Customer or Referral Partner. There is no public
        entry point for this — the caller must already be an authenticated Owner/Employee
        (see docs/decisions/DECISIONS.md #011); `inviter` is that authenticated user, not
        the person being invited.
        """
        if role not in INVITABLE_ROLES:
            raise InvalidRoleForSignupError(f"Signup is not available for role '{role}'.")
        if inviter.role not in INVITER_ROLES_BY_INVITEE_ROLE[role]:
            raise ForbiddenError(f"Your role ('{inviter.role}') cannot invite a '{role}' account.")

        existing = await self._users.find_by_mobile(mobile)
        if existing is not None:
            if existing.status == ACCOUNT_STATUS_ACTIVE:
                raise AlreadyRegisteredError("This mobile number is already registered. Please log in.")
            if existing.role != role:
                raise AlreadyRegisteredError("This mobile number is already registered under a different role.")
            # existing pending_password invite — resend is fine, falls through
        else:
            await self._users.insert(
                User(mobile=mobile, role=role, status=ACCOUNT_STATUS_PENDING_PASSWORD, created_by=inviter.require_id())
            )

        otp = await otp_service.issue_otp(self._redis, mobile=mobile, purpose=OtpPurpose.SIGNUP)
        await self._deliver_otp(mobile, otp)
        await write_audit_log(
            self._db,
            event_type=AuditEvent.OTP_SENT,
            mobile=mobile,
            user_id=inviter.require_id(),
            metadata={"purpose": OtpPurpose.SIGNUP, "invited_role": role},
        )
        return otp if self._dev_otp_echo_enabled() else None

    async def forgot_password(self, *, mobile: str) -> str | None:
        user = await self._users.find_by_mobile(mobile)
        if user is None or user.status != ACCOUNT_STATUS_ACTIVE:
            # Deliberately silent — don't reveal account existence.
            return None

        otp = await otp_service.issue_otp(self._redis, mobile=mobile, purpose=OtpPurpose.FORGOT_PASSWORD)
        await self._deliver_otp(mobile, otp)
        await write_audit_log(
            self._db, event_type=AuditEvent.OTP_SENT, mobile=mobile, metadata={"purpose": OtpPurpose.FORGOT_PASSWORD}
        )
        return otp if self._dev_otp_echo_enabled() else None

    async def verify_otp(self, *, mobile: str, otp: str, purpose: str) -> tuple[str, bool]:
        try:
            await otp_service.verify_stored_otp(self._redis, mobile=mobile, purpose=purpose, otp=otp)
        except otp_service.OtpNotFoundError:
            # On FORGOT_PASSWORD, "no OTP was ever stored" only happens for a mobile
            # `forgot_password` silently declined to send one to (no account, or account
            # not active — see forgot_password above). Letting that raise a distinct
            # otp_not_found here, instead of the otp_mismatch a real account's wrong
            # code gets, would tell an attacker which mobile numbers have accounts.
            # Re-raised as the same error a genuine wrong code produces.
            if purpose == OtpPurpose.FORGOT_PASSWORD:
                raise otp_service.OtpMismatchError("Incorrect OTP.") from None
            raise

        user = await self._users.find_by_mobile(mobile)
        is_new_user = (
            purpose == OtpPurpose.SIGNUP and user is not None and user.status == ACCOUNT_STATUS_PENDING_PASSWORD
        )

        if user is not None and not user.is_mobile_verified:
            await self._users.update(user.require_id(), {"is_mobile_verified": True})

        await write_audit_log(self._db, event_type=AuditEvent.OTP_VERIFIED, mobile=mobile, metadata={"purpose": purpose})

        ticket = create_otp_verified_token(mobile, claims={"purpose": purpose, "jti": secrets.token_urlsafe(16)})
        return ticket, is_new_user

    # ---------------------------------------------------------------- password set/reset/change

    async def consume_otp_verified_ticket(self, otp_verified_token: str, *, expected_purposes: tuple[str, ...]) -> str:
        """Decodes an OTP-verified ticket (see `verify_otp`) and marks it single-use via
        Redis, raising `InvalidTicketError` if it's invalid, expired, already spent, or
        was issued for a purpose this caller doesn't accept. `reset_password` (the one
        caller) accepts both SIGNUP and FORGOT_PASSWORD tickets — the frontend and every
        OTP-invite flow route both "complete my first-time signup" and "I forgot my
        password" through this same endpoint (see docs/AUTHENTICATION.md). This is safe:
        a SIGNUP-purpose ticket can only ever exist for a mobile whose account is NOT yet
        active — `send_otp` refuses to issue a signup OTP to an already-active account
        (`AlreadyRegisteredError`), and `verify_otp` checks the presented OTP against the
        Redis key it was actually issued under (`purpose` included), so a purpose can
        never be laundered from one flow into the other at verify time. A SIGNUP ticket
        therefore can never be used to overwrite an existing active account's password.
        Extracted out of `reset_password` so the replay-protection logic has one place to
        live if another caller ever needs the same "prove this OTP was verified" check.
        Returns the verified mobile number."""
        try:
            payload = decode_token(otp_verified_token, TokenType.OTP_VERIFIED)
        except TokenError as exc:
            raise InvalidTicketError("This link/ticket is invalid or has expired.") from exc

        if payload.get("purpose") not in expected_purposes:
            raise InvalidTicketError("This link/ticket is invalid or has expired.")

        jti = payload.get("jti")
        used_key = f"{_USED_TICKET_KEY_PREFIX}:{jti}"
        first_use = await self._redis.set(used_key, 1, nx=True, ex=60 * 60)
        if not first_use:
            raise InvalidTicketError("This link/ticket has already been used.")

        return payload["sub"]

    async def activate_user_with_password(self, *, mobile: str, new_password: str) -> User:
        """Sets a password and marks the account active + mobile-verified — the shared
        "OTP already proven, now finish setting the account up" step behind both
        `reset_password` below and `CustomerService.complete_direct_registration`
        (production Customer self-registration), so this logic exists in one place."""
        user = await self._users.find_by_mobile(mobile)
        if user is None:
            raise InvalidTicketError("Account no longer exists.")

        await self._users.update(
            user.require_id(),
            {
                "password_hash": hash_password(new_password),
                "status": ACCOUNT_STATUS_ACTIVE,
                "is_mobile_verified": True,
            },
        )
        # A password reset must invalidate every session/refresh token issued under the
        # OLD password — otherwise anyone holding a stolen refresh token (the whole
        # reason a user might reset their password) simply keeps their access. No-op for
        # a brand-new account (no prior sessions exist yet).
        await self._revoke_all_sessions(user.require_id())
        await write_audit_log(self._db, event_type=AuditEvent.PASSWORD_RESET, user_id=user.require_id(), mobile=mobile)
        updated = await self._users.find_by_id(user.require_id())
        assert updated is not None
        return updated

    async def _revoke_all_sessions(self, user_id: str) -> None:
        sessions = await self._sessions.find_many({"user_id": user_id, "status": SESSION_STATUS_ACTIVE}, limit=200)
        for session in sessions:
            await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_LOGGED_OUT, "logout_at": utc_now()})

    async def reset_password(self, *, otp_verified_token: str, new_password: str) -> None:
        """The one endpoint behind both "complete my first-time signup" (SIGNUP-purpose
        ticket) and "I forgot my password" (FORGOT_PASSWORD-purpose ticket) — see
        `consume_otp_verified_ticket`'s docstring for why accepting either is safe."""
        mobile = await self.consume_otp_verified_ticket(otp_verified_token, expected_purposes=OtpPurpose.ALL)
        await self.activate_user_with_password(mobile=mobile, new_password=new_password)

    async def change_password(self, *, user_id: str, current_password: str, new_password: str) -> None:
        user = await self._users.find_by_id(user_id)
        if user is None or user.password_hash is None or not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect.")

        await self._users.update(user.require_id(), {"password_hash": hash_password(new_password), "must_change_password": False})
        await write_audit_log(self._db, event_type=AuditEvent.PASSWORD_CHANGE, user_id=user.require_id(), mobile=user.mobile)

    # ---------------------------------------------------------------- login / logout / refresh

    async def login(self, *, mobile: str, password: str, ctx: RequestContext) -> LoginResponse:
        if await lockout_service.is_locked(self._redis, mobile):
            raise AccountLockedError("Account is temporarily locked due to too many failed attempts.")

        user = await self._users.find_by_mobile(mobile)
        failure_reason = self._login_failure_reason(user, password)

        if failure_reason is not None:
            just_locked = await lockout_service.register_failed_attempt(self._redis, mobile)
            await write_audit_log(
                self._db, event_type=AuditEvent.FAILED_LOGIN, mobile=mobile, metadata={"reason": failure_reason}
            )
            if just_locked:
                await write_audit_log(self._db, event_type=AuditEvent.ACCOUNT_LOCK, mobile=mobile)
            raise InvalidCredentialsError("Invalid mobile number or password.")

        assert user is not None  # narrowed by _login_failure_reason returning None only when valid
        await lockout_service.reset_attempts(self._redis, mobile)

        return await self.issue_session(user=user, ctx=ctx, login_method=LoginMethod.PASSWORD)

    async def issue_session(self, *, user: User, ctx: RequestContext, login_method: str) -> LoginResponse:
        """Mints an access/refresh token pair + `Session` row for an already-trusted
        `user` — the same mechanics `login()` uses after password verification,
        extracted so a caller that has established trust some other way (e.g. Owner
        first-run registration — see OwnerService.register_owner) can reuse it without
        duplicating token/session/audit-log logic. `login_method` is stamped onto the
        `Session` row so the two are always distinguishable in
        Session/audit-log history."""
        user_id = user.require_id()
        family_id = secrets.token_urlsafe(16)
        token_id = secrets.token_urlsafe(16)
        access_token = create_access_token(user_id, claims={"role": user.role})
        refresh_token = create_refresh_token(user_id, claims={"jti": token_id})

        ua = parse_user_agent(ctx.user_agent)
        location = await self._lookup_geo(ctx.ip_address)
        now = utc_now()
        session_id = await self._sessions.insert(
            Session(
                user_id=user_id,
                family_id=family_id,
                token_id=token_id,
                refresh_token_hash=hash_value(refresh_token),
                login_method=login_method,
                device=ua.device,
                browser=ua.browser,
                operating_system=ua.operating_system,
                ip_address=ctx.ip_address,
                city=location.city if location else None,
                country=location.country if location else None,
                login_at=now,
                last_activity_at=now,
                status=SESSION_STATUS_ACTIVE,
            )
        )
        await write_audit_log(
            self._db,
            event_type=AuditEvent.LOGIN,
            user_id=user_id,
            mobile=user.mobile,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            metadata={"session_id": session_id, "login_method": login_method},
        )

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._access_token_ttl_seconds(),
            role=user.role,
            user_id=user_id,
            must_change_password=user.must_change_password,
        )

    async def logout(self, *, user_id: str, refresh_token: str, reason: str = "manual") -> None:
        session = await self._session_from_refresh_token(refresh_token)
        if session is not None and session.user_id == user_id:
            await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_LOGGED_OUT, "logout_at": utc_now()})
        event_type = AuditEvent.AUTO_LOGOUT if reason == "idle_timeout" else AuditEvent.LOGOUT
        await write_audit_log(self._db, event_type=event_type, user_id=user_id)

    # ---------------------------------------------------------------- self-service session management

    async def list_own_sessions(self, user_id: str) -> list[Session]:
        """Every role's own Active Sessions page (Owner/Employee/Referral Partner/
        Customer alike) — the Employee-admin equivalent (viewing an *other* Employee's
        sessions) stays in the employee feature, unchanged, since that's Owner-only
        oversight rather than self-service."""
        return await self._sessions.find_many({"user_id": user_id}, limit=100, sort=[("login_at", -1)])

    async def revoke_own_session(self, *, user_id: str, session_id: str) -> None:
        session = await self._sessions.find_by_id(session_id)
        if session is None or session.user_id != user_id:
            raise NotFoundError("Session not found.")
        if session.status == SESSION_STATUS_ACTIVE:
            await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_LOGGED_OUT, "logout_at": utc_now()})
        await write_audit_log(
            self._db, event_type=AuditEvent.LOGOUT, user_id=user_id, metadata={"session_id": session_id, "revoked_via": "sessions_page"}
        )

    async def logout_all_other_sessions(self, *, user_id: str, current_refresh_token: str | None) -> int:
        """"Logout All Other Devices" — revokes every one of the caller's active
        sessions except the one making this request (identified by its own refresh
        token, when provided), so it can't log the calling device itself out."""
        current_session = await self._session_from_refresh_token(current_refresh_token) if current_refresh_token else None
        sessions = await self._sessions.find_many({"user_id": user_id, "status": SESSION_STATUS_ACTIVE}, limit=200)
        revoked_count = 0
        for session in sessions:
            if current_session is not None and session.require_id() == current_session.require_id():
                continue
            await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_LOGGED_OUT, "logout_at": utc_now()})
            revoked_count += 1
        await write_audit_log(
            self._db, event_type=AuditEvent.LOGOUT, user_id=user_id, metadata={"logout_all_other_devices": True, "count": revoked_count}
        )
        return revoked_count

    async def refresh(self, *, refresh_token: str, ctx: RequestContext) -> TokenPairResponse:
        """Rotates the refresh token, chaining the new session row into the same
        `family_id`. If the presented token belongs to a row already marked ROTATED
        (i.e. it was valid once but has already been superseded), that's a stolen/replayed
        token — the entire family is revoked rather than just rejecting this one request.
        See docs/decisions/DECISIONS.md #013.
        """
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except TokenError as exc:
            raise InvalidRefreshTokenError("Invalid or expired refresh token.") from exc

        session = await self._sessions.find_by_token_id(payload.get("jti", ""))
        if session is None:
            raise InvalidRefreshTokenError("Invalid refresh token.")

        if session.status == SESSION_STATUS_ROTATED:
            await self._sessions.revoke_family(session.family_id)
            await write_audit_log(
                self._db,
                event_type=AuditEvent.SUSPICIOUS_REFRESH_REUSE,
                user_id=session.user_id,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
                metadata={"family_id": session.family_id},
            )
            raise InvalidRefreshTokenError("Invalid refresh token.")

        if session.status != SESSION_STATUS_ACTIVE:
            raise InvalidRefreshTokenError("Session no longer active.")

        user = await self._users.find_by_id(session.user_id)
        if user is None or user.status != ACCOUNT_STATUS_ACTIVE:
            raise InvalidRefreshTokenError("Account no longer active.")

        user_id = user.require_id()
        new_token_id = secrets.token_urlsafe(16)
        access_token = create_access_token(user_id, claims={"role": user.role})
        new_refresh_token = create_refresh_token(user_id, claims={"jti": new_token_id})

        await self._sessions.update(session.require_id(), {"status": SESSION_STATUS_ROTATED})

        ua = parse_user_agent(ctx.user_agent)
        location = await self._lookup_geo(ctx.ip_address)
        await self._sessions.insert(
            Session(
                user_id=user_id,
                family_id=session.family_id,
                token_id=new_token_id,
                refresh_token_hash=hash_value(new_refresh_token),
                login_method=session.login_method,
                device=ua.device,
                browser=ua.browser,
                operating_system=ua.operating_system,
                ip_address=ctx.ip_address,
                city=location.city if location else None,
                country=location.country if location else None,
                login_at=session.login_at,
                last_activity_at=utc_now(),
                status=SESSION_STATUS_ACTIVE,
            )
        )
        await write_audit_log(self._db, event_type=AuditEvent.REFRESH_TOKEN, user_id=user_id)

        return TokenPairResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=self._access_token_ttl_seconds(),
        )

    # ---------------------------------------------------------------- profile

    async def get_profile(self, *, user_id: str) -> ProfileResponse:
        user = await self._users.find_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("Account no longer exists.")

        name: str | None = None
        if user.role == "owner":
            owner_profile = await self._owner_profiles.find_by_user_id(user_id)
            name = owner_profile.full_name if owner_profile else None
        elif user.role == "employee":
            employee = await self._employees.find_by_user_id(user_id)
            name = employee.display_name if employee else None

        return ProfileResponse(
            user_id=user.require_id(),
            mobile=user.mobile,
            role=user.role,
            status=user.status,
            is_mobile_verified=user.is_mobile_verified,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            name=name,
        )

    # ---------------------------------------------------------------- internals

    def _login_failure_reason(self, user: User | None, password: str) -> str | None:
        """Returns None on valid credentials, else a specific reason for the audit log.
        The client-facing error is always the same generic message regardless of which
        reason this returns — only the internal audit trail is detailed (see
        docs/AUTHENTICATION.md's Login History section).
        """
        if user is None:
            return "account_not_found"
        if user.status != ACCOUNT_STATUS_ACTIVE:
            return "account_inactive"
        if user.password_hash is None or not verify_password(password, user.password_hash):
            return "invalid_password"
        return None

    async def _session_from_refresh_token(self, refresh_token: str) -> Session | None:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except TokenError:
            return None
        return await self._sessions.find_by_token_id(payload.get("jti", ""))

    async def _deliver_otp(self, mobile: str, otp: str) -> None:
        if get_settings().otp_mode == "development":
            logger.info("[DEV MODE] Generated OTP %s for mobile %s", otp, mobile)
            return
        try:
            await NotConfiguredSmsClient().send_sms(mobile, f"Your AFS Financial CRM OTP is {otp}")
        except NotImplementedError:
            pass  # no SMS provider configured yet — see docs/KNOWN_LIMITATIONS.md

    async def _lookup_geo(self, ip_address: str | None) -> GeoLocation | None:
        if not ip_address:
            return None
        try:
            return await NotConfiguredGeoIpClient().lookup(ip_address)
        except NotImplementedError:
            return None  # no GeoIP provider configured yet — see docs/KNOWN_LIMITATIONS.md

    def _dev_otp_echo_enabled(self) -> bool:
        # Single source of truth for every OTP dev-mode behavior — see Settings.otp_mode.
        return get_settings().otp_mode == "development"

    def _access_token_ttl_seconds(self) -> int:
        return get_security_policy().access_token_expire_minutes * 60
