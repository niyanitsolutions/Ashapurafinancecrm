"""Login-attempt lockout, Redis-backed (separate from OTP attempt limits in
otp_service.py — this guards password login, not OTP verification). 5 failed attempts
locks the account for 15 minutes; both thresholds are configurable via settings.
"""

from redis.asyncio import Redis

from app.config.security import get_security_policy

_ATTEMPTS_PREFIX = "login_attempts"
_LOCK_PREFIX = "login_lock"


def _attempts_key(mobile: str) -> str:
    return f"{_ATTEMPTS_PREFIX}:{mobile}"


def _lock_key(mobile: str) -> str:
    return f"{_LOCK_PREFIX}:{mobile}"


async def is_locked(redis: Redis, mobile: str) -> bool:
    return bool(await redis.exists(_lock_key(mobile)))


async def register_failed_attempt(redis: Redis, mobile: str) -> bool:
    """Returns True if this attempt just triggered a new lock."""
    policy = get_security_policy()
    lock_seconds = policy.account_lock_minutes * 60

    attempts_key = _attempts_key(mobile)
    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, lock_seconds)

    if attempts >= policy.max_login_attempts:
        await redis.set(_lock_key(mobile), 1, ex=lock_seconds)
        return True
    return False


async def reset_attempts(redis: Redis, mobile: str) -> None:
    await redis.delete(_attempts_key(mobile), _lock_key(mobile))
