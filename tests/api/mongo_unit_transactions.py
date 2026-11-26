"""Unit-only session adapter for mongomock; real Mongo tests prove transaction integrity.

This deliberately does not emulate MongoDB locking, write concern or rollback. Tests
that assert atomicity/concurrency must use the disposable replica-set fixtures.
"""

from functools import wraps

import mongomock
from mongomock_motor import AsyncMongoMockClient


class UnitSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def start_transaction(self):
        return self


def enable_unit_sessions(monkeypatch):
    async def start_session(self):
        return UnitSession()

    monkeypatch.setattr(
        AsyncMongoMockClient, "start_session", start_session, raising=False
    )
    # Strip only this synthetic session, never a real Motor/PyMongo session.
    for name in (
        "insert_one",
        "insert_many",
        "find_one",
        "find",
        "find_one_and_update",
        "update_one",
        "update_many",
        "delete_one",
        "delete_many",
        "count_documents",
        "aggregate",
    ):
        original = getattr(mongomock.collection.Collection, name)

        def adapt(method):
            @wraps(method)
            def call(*args, **kwargs):
                if isinstance(kwargs.get("session"), UnitSession):
                    kwargs.pop("session")
                return method(*args, **kwargs)

            return call

        monkeypatch.setattr(mongomock.collection.Collection, name, adapt(original))
