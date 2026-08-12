"""Auth-module-local constants. Kept inside the feature rather than the global
app/constants/ package because these are Auth's own internal vocabulary, not
cross-cutting keys other features need to reference.
"""

from app.constants.roles import CUSTOMER, EMPLOYEE, OWNER, REFERRAL_PARTNER


class OtpPurpose:
    SIGNUP = "signup"
    FORGOT_PASSWORD = "forgot_password"

    ALL = (SIGNUP, FORGOT_PASSWORD)


# Which roles can ever be created via the OTP-invitation flow, and who is authorized to
# invite each one. There is no public self-signup for any role (see
# docs/decisions/DECISIONS.md #007, #011) — Owner/Employee are provisioned outside Auth
# entirely (seed script / future User Management); Customer and Referral Partner are
# created only when an already-authenticated staff member invites them.
INVITER_ROLES_BY_INVITEE_ROLE: dict[str, frozenset[str]] = {
    CUSTOMER: frozenset({OWNER, EMPLOYEE}),
    REFERRAL_PARTNER: frozenset({OWNER}),
}
INVITABLE_ROLES = tuple(INVITER_ROLES_BY_INVITEE_ROLE.keys())


class LoginMethod:
    PASSWORD = "password"


class AuditEvent:
    LOGIN = "login"
    LOGOUT = "logout"
    AUTO_LOGOUT = "auto_logout"
    FAILED_LOGIN = "failed_login"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    OTP_SENT = "otp_sent"
    OTP_VERIFIED = "otp_verified"
    REFRESH_TOKEN = "refresh_token"
    ACCOUNT_LOCK = "account_lock"
    ACCOUNT_UNLOCK = "account_unlock"
    SUSPICIOUS_REFRESH_REUSE = "suspicious_refresh_reuse"
