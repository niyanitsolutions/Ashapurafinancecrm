"""JWT verification dependency. This only decodes and validates the access token; it
does not know about the `auth` feature's user-lookup or permission model (added when
Authentication is built) — kept minimal so it is safe to wire into `main.py` now.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedError
from app.security.jwt import TokenError, TokenType, decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_subject(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired token.") from exc
    return str(payload["sub"])
