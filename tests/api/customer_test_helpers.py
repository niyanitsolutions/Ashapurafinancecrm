"""Provision historical password customers through the staff invitation API.

Portal/module regressions are not self-registration tests. New PIN registration is
covered independently against real transactional MongoDB, with mocked Airtel.
"""
from app.config.database import get_database
from app.security.jwt import create_access_token


async def start_legacy_customer(client, mobile):
    db = client._transport.app.dependency_overrides[get_database]()
    owner = await db.users.find_one({"role": "owner", "is_deleted": False})
    assert owner, "Legacy-account fixtures require a seeded owner"
    session = await db.sessions.find_one({"user_id": str(owner["_id"]), "status": "active"})
    assert session, "Legacy-account fixtures require an authenticated owner"
    return await client.post("/api/v1/auth/send-otp", json={"mobile": mobile, "role": "customer"},
        headers={"Authorization": "Bearer " + create_access_token(str(owner["_id"]), {"role": "owner", "sid": session["family_id"]})})
