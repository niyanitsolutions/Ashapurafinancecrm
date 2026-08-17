from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorClientSession, AsyncIOMotorDatabase

from app.config.settings import get_settings

_client: AsyncIOMotorClient[Any] | None = None


_SERVER_SELECTION_TIMEOUT_MS = 5000  # fail fast rather than hang if Mongo is unreachable


def get_client() -> AsyncIOMotorClient[Any]:
    global _client
    if _client is None:
        settings = get_settings()
        # tz_aware=True: every datetime BSON round-trips as tz-aware UTC instead of
        # naive. Every write in this app already goes through `utc_now()` (tz-aware),
        # so nothing changes on the write side — this only fixes the *read* side, which
        # previously discarded that information. Naive-but-actually-UTC values were
        # serialized into API responses with no offset marker, which JS's `Date`
        # parsing then silently misreads as browser-local time (see docs/TIMEZONE.md)
        # — this single flag is the root-cause fix for that class of bug.
        _client = AsyncIOMotorClient(
            settings.mongo_uri, serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS, tz_aware=True
        )
    return _client


def get_database() -> AsyncIOMotorDatabase[Any]:
    settings = get_settings()
    return get_client()[settings.mongo_db_name]


async def ping() -> bool:
    result = await get_database().command("ping")
    return bool(result.get("ok") == 1)


@asynccontextmanager
async def start_transaction() -> AsyncIterator[AsyncIOMotorClientSession]:
    """Yields a session with an active multi-document transaction.

    Requires Mongo to be running as a replica set (see deployment/docker-compose.yml).
    Use for flows spanning multiple collections, e.g. lead status change + audit log + notification.
    """
    client = get_client()
    async with await client.start_session() as session, session.start_transaction():
        yield session


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
