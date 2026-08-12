"""Redis-backed rate limiting, fixed-window per client key (IP by default; features that
need per-mobile-number limits, e.g. OTP requests, pass their own key). Applied as a
FastAPI dependency on specific routes rather than globally, since limits differ by
endpoint sensitivity (login/OTP need tighter limits than read-only dashboard calls).

Takes the Redis client via `Depends(get_redis)` rather than calling the module-level
singleton directly — that keeps it swappable through `app.dependency_overrides`, the same
as every other Redis/Mongo consumer, instead of silently bypassing test overrides.
"""

from typing import Annotated, Any

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.config.redis import get_redis
from app.config.settings import get_settings
from app.core.exceptions import RateLimitedError

WINDOW_SECONDS = 60


async def enforce_rate_limit(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
    key_suffix: str | None = None,
    limit: int | None = None,
) -> None:
    settings = get_settings()
    max_requests = limit or settings.rate_limit_per_minute
    client_key = key_suffix or (request.client.host if request.client else "unknown")
    redis_key = f"rate_limit:{request.url.path}:{client_key}"

    current = await redis.incr(redis_key)
    if current == 1:
        await redis.expire(redis_key, WINDOW_SECONDS)
    if current > max_requests:
        raise RateLimitedError("Too many requests, please slow down.")


def rate_limited(limit: int | None = None) -> Any:
    async def dependency(request: Request, redis: Annotated[Redis, Depends(get_redis)]) -> None:
        await enforce_rate_limit(request, redis, limit=limit)

    return Depends(dependency)
