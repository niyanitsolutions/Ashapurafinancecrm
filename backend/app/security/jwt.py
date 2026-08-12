from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.config.security import get_security_policy


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    OTP_VERIFIED = "otp_verified"  # short-lived ticket proving OTP was verified; see auth feature


class TokenError(Exception):
    pass


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    return _create_token(subject, TokenType.ACCESS, claims)


def create_refresh_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    return _create_token(subject, TokenType.REFRESH, claims)


def create_otp_verified_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    return _create_token(subject, TokenType.OTP_VERIFIED, claims)


def _expiry_for(token_type: TokenType, policy: Any) -> timedelta:
    if token_type is TokenType.ACCESS:
        return timedelta(minutes=policy.access_token_expire_minutes)
    if token_type is TokenType.REFRESH:
        return timedelta(days=policy.refresh_token_expire_days)
    return timedelta(minutes=policy.otp_verified_token_expire_minutes)


def _create_token(subject: str, token_type: TokenType, claims: dict[str, Any] | None) -> str:
    policy = get_security_policy()
    now = datetime.now(UTC)
    expires_delta = _expiry_for(token_type, policy)
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        **(claims or {}),
    }
    return jwt.encode(payload, policy.jwt_secret_key, algorithm=policy.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    policy = get_security_policy()
    try:
        payload = jwt.decode(token, policy.jwt_secret_key, algorithms=[policy.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise TokenError(f"expected token type '{expected_type.value}', got '{payload.get('type')}'")
    return payload
