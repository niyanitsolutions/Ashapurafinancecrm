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
        _client = AsyncIOMotorClient(
            settings.mongo_uri, serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS
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
