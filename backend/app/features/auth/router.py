from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.response import ApiResponse
from app.features.auth.dependencies import (
    get_auth_service,
    get_current_active_user,
    get_request_context,
)
from app.features.auth.models import Session, User
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
    result = await auth.login(mobile=payload.mobile, password=payload.password, ctx=ctx)
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
