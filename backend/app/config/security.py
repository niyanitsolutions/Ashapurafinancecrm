"""Security policy configuration consumed by the app.security package.

Holds *policy values* (expiry windows, algorithms, thresholds) sourced from Settings.
Actual crypto/JWT/OTP logic lives in app.security, not here.
"""

from dataclasses import dataclass

from app.config.settings import get_settings


@dataclass(frozen=True)
class SecurityPolicy:
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    otp_expire_minutes: int
    otp_max_attempts: int
    max_login_attempts: int
    account_lock_minutes: int
    secure_link_expire_minutes: int
    otp_verified_token_expire_minutes: int


def get_security_policy() -> SecurityPolicy:
    settings = get_settings()
    return SecurityPolicy(
        jwt_secret_key=settings.jwt_secret_key,
        jwt_algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
        otp_expire_minutes=settings.otp_expire_minutes,
        otp_max_attempts=settings.otp_max_attempts,
        max_login_attempts=settings.max_login_attempts,
        account_lock_minutes=settings.account_lock_minutes,
        secure_link_expire_minutes=settings.secure_link_expire_minutes,
        otp_verified_token_expire_minutes=settings.otp_verified_token_expire_minutes,
    )
