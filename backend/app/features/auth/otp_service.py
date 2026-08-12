"""Redis-backed OTP issuance/verification. OTPs never touch MongoDB — see
docs/SECURITY.md. Uses the generation/hashing primitives from app.security.otp; this
module owns only the Redis storage shape, expiry, and attempt-limit enforcement.
"""

from fastapi import status
from redis.asyncio import Redis

from app.config.security import get_security_policy
from app.config.settings import get_settings
from app.core.exceptions import AppError
from app.security.otp import generate_otp, hash_otp, verify_otp

_KEY_PREFIX = "otp"

# Fixed, well-known OTP used only when Settings.otp_mode == "development" — see
# issue_otp below. Never used in production; the pattern validator on Settings.otp_mode
# is the only thing standing between this and a real deployment, so it defaults to
# "production" (safe) rather than "development".
_DEV_MODE_OTP = "123456"


class OtpNotFoundError(AppError):
    code = "otp_not_found"  # never sent, or expired
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class OtpMaxAttemptsError(AppError):
    code = "otp_max_attempts_exceeded"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


class OtpMismatchError(AppError):
    code = "otp_mismatch"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


def _key(purpose: str, mobile: str) -> str:
    return f"{_KEY_PREFIX}:{purpose}:{mobile}"


async def issue_otp(redis: Redis, *, mobile: str, purpose: str) -> str:
    """Generates and stores a new OTP, overwriting any prior one for this mobile+purpose
    (each send-otp/forgot-password call issues a fresh code and resets the attempt count).
    Returns the raw OTP for the caller to deliver via SMS.

    In `Settings.otp_mode == "development"` the value is the fixed `_DEV_MODE_OTP`
    instead of a random one — storage, hashing, expiry, and attempt-limiting below are
    identical either way, and `verify_stored_otp` never knows or cares which mode
    produced the value it's comparing against. Only the *source* of the OTP value
    changes; the whole verification architecture stays exactly as production uses it.
    """
    policy = get_security_policy()
    otp = _DEV_MODE_OTP if get_settings().otp_mode == "development" else generate_otp()
    key = _key(purpose, mobile)
    await redis.hset(key, mapping={"otp_hash": hash_otp(otp), "attempts": 0})  # type: ignore[misc]  # redis-py async stub returns Awaitable|Any
    await redis.expire(key, policy.otp_expire_minutes * 60)
    return otp


async def verify_stored_otp(redis: Redis, *, mobile: str, purpose: str, otp: str) -> None:
    """Raises an OtpError subclass on failure; returns normally on success and consumes
    (deletes) the OTP so it can't be replayed.
    """
    policy = get_security_policy()
    key = _key(purpose, mobile)
    stored = await redis.hgetall(key)  # type: ignore[misc]  # redis-py async stub returns Awaitable|Any
    if not stored:
        raise OtpNotFoundError("OTP not found or expired. Request a new one.")

    attempts = int(stored.get("attempts", 0))
    if attempts >= policy.otp_max_attempts:
        await redis.delete(key)
        raise OtpMaxAttemptsError("Maximum OTP attempts exceeded. Request a new one.")

    if not verify_otp(otp, stored["otp_hash"]):
        await redis.hincrby(key, "attempts", 1)  # type: ignore[misc]  # redis-py async stub returns Awaitable|Any
        raise OtpMismatchError("Incorrect OTP.")

    await redis.delete(key)
