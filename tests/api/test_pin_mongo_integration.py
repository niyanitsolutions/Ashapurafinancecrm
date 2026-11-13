"""Opt-in atomicity checks using only a disposable loopback MongoDB database."""

import asyncio
import os
from uuid import uuid4

import pytest
from app.core.exceptions import AppError
from app.features.auth.indexes import ensure_auth_indexes
from app.features.auth.models import User
from app.features.auth.pin_service import Complete, PinService, Start, Verify
from app.features.auth.service import AuthService, RequestContext
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.uri_parser import parse_uri


@pytest.fixture
async def pin_mongo():
    uri = os.environ.get("AFS_PIN_TEST_MONGO_URI")
    if not uri:
        pytest.skip(
            "Set AFS_PIN_TEST_MONGO_URI to a disposable loopback MongoDB server"
        )
    assert all(
        host in {"localhost", "127.0.0.1", "::1"}
        for host, _ in parse_uri(uri)["nodelist"]
    )
    connection = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=2000)
    await connection.admin.command("ping")
    name = "afs_pin_test_" + uuid4().hex
    db = connection[name]
    try:
        await ensure_auth_indexes(db)
        yield db
    finally:
        assert db.name == name and name.startswith("afs_pin_test_")
        await connection.drop_database(name)
        connection.close()


async def test_real_mongo_concurrent_resend_verify_complete_and_login(
    pin_mongo, mock_redis, monkeypatch
):
    from app.features.auth import pin_service

    db = pin_mongo
    mobile = "9000000077"
    user = User(mobile=mobile, role="customer", status="active")
    await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    # The transport stays mocked. Only MongoDB operations are real.
    auth = AuthService(db, mock_redis)
    service = PinService(auth)
    ctx = RequestContext(ip_address="127.0.0.1", user_agent="test")

    async def capture_start():
        try:
            return await service.start(
                Start(mobile=mobile, purpose="FIRST_TIME_LOGIN"), ctx
            )
        except AppError:
            return None

    results = await asyncio.gather(*(capture_start() for _ in range(4)))
    assert sum(r is not None for r in results) == 1
    challenge = next(r["challenge_id"] for r in results if r)
    # Mark this fixture as accepted with a known hashed code, without any SMS call.
    await db.auth_pin_challenges.update_one(
        {"challenge_id": challenge},
        {
            "$set": {
                "state": "issued",
                "otp_hash": pin_service.otp_digest(challenge, "8621"),
            }
        },
    )

    async def verify():
        try:
            return await service.verify(
                Verify(
                    mobile=mobile,
                    purpose="FIRST_TIME_LOGIN",
                    challenge_id=challenge,
                    otp="8621",
                ),
                ctx,
            )
        except AppError:
            return None

    results = await asyncio.gather(*(verify() for _ in range(4)))
    assert sum(r is not None for r in results) == 1
    token = next(r["authorization"] for r in results if r)

    async def complete():
        try:
            return await service.complete(
                Complete(authorization=token, pin="0472", confirm_pin="0472"), ctx
            )
        except AppError:
            return None

    results = await asyncio.gather(*(complete() for _ in range(4)))
    assert sum(r is not None for r in results) == 1
    assert await db.sessions.count_documents({"status": "active"}) == 1

    async def wrong_pin():
        try:
            await service.login(pin_service.Login(mobile=mobile, pin="9999"), ctx)
        except AppError:
            return
        raise AssertionError("Wrong PIN authenticated")

    await asyncio.gather(*(wrong_pin() for _ in range(8)))
    saved = await db.users.find_one({"mobile": mobile})
    assert saved["failed_pin_attempts"] == 5 and saved["pin_locked_until"] is not None
