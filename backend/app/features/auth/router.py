from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.dependencies import (
    get_auth_service,
    get_current_active_user,
    get_request_context,
)
from app.features.auth.models import Session, User
from app.features.auth.pin_service import Complete as PinComplete
from app.features.auth.pin_service import Login as PinLogin
from app.features.auth.pin_service import PinService
from app.features.auth.pin_service import Start as PinStart
from app.features.auth.pin_service import Verify as PinVerify
from app.features.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GenericOtpSentResponse,
    LoginRequest,
    LoginResponse,
    LogoutAllRequest,
    LogoutAllResponse,
    LogoutRequest,
    ProfileResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SendOtpRequest,
    SessionSummary,
    TokenPairResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.features.auth.service import AuthService, RequestContext
from app.middleware.rate_limit import rate_limited

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]


@router.post("/send-otp", dependencies=[rate_limited(limit=5)])
async def send_otp(
    payload: SendOtpRequest, auth: AuthServiceDep, current_user: CurrentUserDep
) -> ApiResponse[GenericOtpSentResponse]:
    """Owner/Employee-only — there is no public signup entry point (decision 011)."""
    dev_otp = await auth.send_otp(mobile=payload.mobile, role=payload.role, inviter=current_user)
    return ApiResponse[GenericOtpSentResponse].ok(GenericOtpSentResponse(dev_otp=dev_otp))


@router.post("/forgot-password", dependencies=[rate_limited(limit=5)])
async def forgot_password(payload: ForgotPasswordRequest, auth: AuthServiceDep) -> ApiResponse[GenericOtpSentResponse]:
    dev_otp = await auth.forgot_password(mobile=payload.mobile)
    return ApiResponse[GenericOtpSentResponse].ok(GenericOtpSentResponse(dev_otp=dev_otp))


@router.post("/verify-otp", dependencies=[rate_limited(limit=10)])
async def verify_otp(payload: VerifyOtpRequest, auth: AuthServiceDep) -> ApiResponse[VerifyOtpResponse]:
    ticket, is_new_user = await auth.verify_otp(mobile=payload.mobile, otp=payload.otp, purpose=payload.purpose)
    return ApiResponse[VerifyOtpResponse].ok(VerifyOtpResponse(otp_verified_token=ticket, is_new_user=is_new_user))


@router.post("/reset-password", dependencies=[rate_limited(limit=10)])
async def reset_password(payload: ResetPasswordRequest, auth: AuthServiceDep) -> ApiResponse[None]:
    await auth.reset_password(otp_verified_token=payload.otp_verified_token, new_password=payload.new_password)
    return ApiResponse[None].ok()


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest, auth: AuthServiceDep, current_user: CurrentUserDep
) -> ApiResponse[None]:
    await auth.change_password(
        user_id=current_user.require_id(),
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return ApiResponse[None].ok()


@router.post("/login", dependencies=[rate_limited(limit=10)])
async def login(payload: LoginRequest, auth: AuthServiceDep, ctx: RequestContextDep) -> ApiResponse[LoginResponse]:
    result = await auth.login(
        mobile=payload.mobile, password=payload.password, ctx=ctx, latitude=payload.latitude, longitude=payload.longitude
    )
    return ApiResponse[LoginResponse].ok(result)


@router.post("/logout")
async def logout(payload: LogoutRequest, auth: AuthServiceDep, current_user: CurrentUserDep) -> ApiResponse[None]:
    await auth.logout(user_id=current_user.require_id(), refresh_token=payload.refresh_token, reason=payload.reason)
    return ApiResponse[None].ok()


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest, auth: AuthServiceDep, ctx: RequestContextDep
) -> ApiResponse[TokenPairResponse]:
    result = await auth.refresh(refresh_token=payload.refresh_token, ctx=ctx)
    return ApiResponse[TokenPairResponse].ok(result)


@router.get("/profile")
async def get_profile(auth: AuthServiceDep, current_user: CurrentUserDep) -> ApiResponse[ProfileResponse]:
    result = await auth.get_profile(user_id=current_user.require_id())
    return ApiResponse[ProfileResponse].ok(result)


# ---------------------------------------------------------------------- self-service session management
# Role-agnostic — every role's own "Active Sessions" page (Owner/Employee/Referral
# Partner/Customer alike). The Employee-admin equivalent (Owner viewing an *other*
# Employee's sessions) stays in the employee feature, unchanged.


@router.get("/sessions")
async def list_own_sessions(auth: AuthServiceDep, current_user: CurrentUserDep) -> ApiResponse[list[SessionSummary]]:
    sessions = await auth.list_own_sessions(current_user.require_id())
    return ApiResponse[list[SessionSummary]].ok([_session_summary(s) for s in sessions])


@router.post("/sessions/{session_id}/revoke")
async def revoke_own_session(session_id: str, auth: AuthServiceDep, current_user: CurrentUserDep) -> ApiResponse[None]:
    await auth.revoke_own_session(user_id=current_user.require_id(), session_id=session_id)
    return ApiResponse[None].ok()


@router.post("/logout-all")
async def logout_all_other_sessions(
    payload: LogoutAllRequest, auth: AuthServiceDep, current_user: CurrentUserDep
) -> ApiResponse[LogoutAllResponse]:
    count = await auth.logout_all_other_sessions(user_id=current_user.require_id(), current_refresh_token=payload.refresh_token)
    return ApiResponse[LogoutAllResponse].ok(LogoutAllResponse(revoked_count=count))


def _session_summary(session: Session) -> SessionSummary:
    return SessionSummary(
        id=session.require_id(),
        device=session.device,
        browser=session.browser,
        operating_system=session.operating_system,
        ip_address=session.ip_address,
        city=session.city,
        country=session.country,
        login_at=session.login_at,
        last_activity_at=session.last_activity_at,
        status=session.status,
    )


@router.post("/activity")
async def activity(current_user: CurrentUserDep) -> ApiResponse[dict[str, bool]]:
    """Called on visible user interaction; polling/refresh never extends idle time."""
    return ApiResponse[dict[str, bool]].ok({"active": True})


@router.get("/pin/policy")
async def pin_policy(auth: AuthServiceDep) -> ApiResponse[dict[str, Any]]:
    from app.features.auth.pin_service import policy

    return ApiResponse.ok({"mode": await policy(auth._db)})


@router.post("/pin/start", dependencies=[rate_limited(limit=10)])
async def pin_start(
    payload: PinStart, auth: AuthServiceDep, ctx: RequestContextDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await PinService(auth).start(payload, ctx))


@router.post("/pin/verify", dependencies=[rate_limited(limit=30)])
async def pin_verify(
    payload: PinVerify, auth: AuthServiceDep, ctx: RequestContextDep
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse.ok(await PinService(auth).verify(payload, ctx))


@router.post("/pin/complete", dependencies=[rate_limited(limit=20)])
async def pin_complete(
    payload: PinComplete, auth: AuthServiceDep, ctx: RequestContextDep
) -> ApiResponse[Any]:
    return ApiResponse.ok(await PinService(auth).complete(payload, ctx))


@router.post("/pin/login", dependencies=[rate_limited(limit=20)])
async def pin_login(payload: PinLogin, auth: AuthServiceDep, ctx: RequestContextDep) -> ApiResponse[Any]:
    return ApiResponse.ok(await PinService(auth).login(payload, ctx))


@router.post("/pin/cutover")
async def pin_cutover(auth: AuthServiceDep, actor: CurrentUserDep) -> ApiResponse[dict[str, Any]]:
    from app.core.exceptions import ConflictError, ForbiddenError
    from app.shared.audit_log import write_audit_log

    if actor.role != "owner":
        raise ForbiddenError("Owner access is required.")
    outstanding = await auth._db.users.count_documents(
        {
            "role": "customer",
            "status": "active",
            "is_deleted": False,
            "$or": [{"pin_hash": None}, {"pin_hash": {"$exists": False}}],
        }
    )
    ready = await auth._db.integration_configs.find_one(
        {
            "provider": "airtel_iq",
            "integration_type": "sms",
            "is_active": True,
            "is_enabled": True,
            "is_deleted": False,
            "last_success_at": {"$ne": None},
        }
    )
    if outstanding or not ready:
        raise ConflictError(
            "Enroll every active customer account and successfully test/activate Airtel before PIN-only cutover."
        )
    await auth._db.auth_login_policy.update_one(
        {"_id": "default"},
        {"$set": {"mode": "pin_only", "scope": "customer", "updated_by": actor.require_id()}},
        upsert=True,
    )
    await write_audit_log(auth._db, event_type="pin_only_cutover", user_id=actor.require_id(), metadata={"scope":"customer"})
    return ApiResponse.ok({"mode": "pin_only"})
