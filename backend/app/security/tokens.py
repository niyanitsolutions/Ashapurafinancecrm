"""Secure-link tokens for the two-tier Customer/Referral Partner auth model: a scoped,
expiring, single-purpose token that lets a customer open their assigned form without a
password, separate from the full mobile+password account (see app.security.jwt +
app.security.password for that). Distinct from jwt.py because these tokens are scoped to
one resource (e.g. one lead's application form) rather than a user session.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config.security import get_security_policy


class SecureLinkError(Exception):
    pass


def issue_secure_link_token(resource_type: str, resource_id: str, extra_claims: dict[str, Any] | None = None) -> str:
    policy = get_security_policy()
    now = datetime.now(UTC)
    payload = {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(minutes=policy.secure_link_expire_minutes),
        **(extra_claims or {}),
    }
    return jwt.encode(payload, policy.jwt_secret_key, algorithm=policy.jwt_algorithm)


def decode_secure_link_token(token: str) -> dict[str, Any]:
    policy = get_security_policy()
    try:
        return jwt.decode(token, policy.jwt_secret_key, algorithms=[policy.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise SecureLinkError(str(exc)) from exc
