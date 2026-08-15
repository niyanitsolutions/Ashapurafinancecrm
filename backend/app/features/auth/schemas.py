from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.features.auth.constants import OtpPurpose
from app.security.password import PasswordStr

# Same shape as utils.validation.is_valid_mobile — kept as a literal pattern here (rather
# than importing that function) so schema validation stays declarative/OpenAPI-visible.
MobileStr = Annotated[str, Field(pattern=r"^[6-9]\d{9}$")]


class SendOtpRequest(BaseModel):
    mobile: MobileStr
    role: str  # must be in SELF_SIGNUP_ROLES; this endpoint is signup-only


class ForgotPasswordRequest(BaseModel):
    mobile: MobileStr


class GenericOtpSentResponse(BaseModel):
    message: str = "If the account is eligible, an OTP has been sent."
    # Populated only outside production — see docs/KNOWN_LIMITATIONS.md (no SMS
    # provider configured yet). Always null in production regardless of request.
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    mobile: MobileStr
    otp: str = Field(pattern=r"^\d{6}$")
    purpose: str = Field(pattern=f"^({'|'.join(OtpPurpose.ALL)})$")


class VerifyOtpResponse(BaseModel):
    otp_verified_token: str
    is_new_user: bool


class ResetPasswordRequest(BaseModel):
    otp_verified_token: str
    new_password: PasswordStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: PasswordStr


class LoginRequest(BaseModel):
    mobile: MobileStr
    password: str
    # Optional — only meaningful for an Employee actor when an Owner has configured an
    # active Geo Fence with "login" in its allowed_activities (see
    # geo_fencing/enforcement.py::enforce_geo_fence, reused as-is from AuthService.login).
    # Owner/Customer/Referral Partner logins are unaffected either way.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, seconds


class LoginResponse(TokenPairResponse):
    role: str
    user_id: str
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
    # Stamped onto the audit log entry (AuditEvent.LOGOUT vs. AUTO_LOGOUT) — never
    # affects what actually happens (the session is revoked either way).
    reason: str = Field(default="manual", pattern=r"^(manual|idle_timeout)$")


class LogoutAllRequest(BaseModel):
    # Optional — when present, that session is excluded from the revoke so "Logout All
    # Other Devices" doesn't also kill the tab the customer is sitting in.
    refresh_token: str | None = None


class LogoutAllResponse(BaseModel):
    revoked_count: int


class SessionSummary(BaseModel):
    """Same shape as employee/schemas.py's own SessionSummary (that one stays
    Owner/Employee-admin-only, viewing an Employee record's sessions) — this is the
    self-service, role-agnostic equivalent every role (Owner/Employee/Referral Partner/
    Customer) uses for their own Active Sessions page."""

    id: str
    device: str | None
    browser: str | None
    operating_system: str | None
    ip_address: str | None
    city: str | None
    country: str | None
    login_at: datetime
    last_activity_at: datetime
    status: str


class ProfileResponse(BaseModel):
    user_id: str
    mobile: str
    role: str
    status: str
    is_mobile_verified: bool
    must_change_password: bool
    created_at: datetime
    # Owner -> owner_profiles.full_name, Employee -> employees.display_name. None if no
    # matching profile document exists yet (e.g. a legacy/grandfathered Owner row) —
    # callers must not assume this is always populated.
    name: str | None = None
