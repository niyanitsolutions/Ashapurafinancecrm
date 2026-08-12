from redis.asyncio import Redis

from app.config.settings import get_settings

_redis: Redis | None = None

_SOCKET_CONNECT_TIMEOUT_S = 5  # fail fast rather than hang if Redis is unreachable


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT_S,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
