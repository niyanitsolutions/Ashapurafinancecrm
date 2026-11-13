"""PIN flows use captured mocked transport only; never contact an SMS provider."""

import asyncio
import json
from datetime import timedelta

import pytest
from app.features.auth import pin_service
from app.features.auth.models import User
from app.features.integrations.airtel_iq import DEFAULTS
from app.security.encryption import encrypt
from app.security.password import hash_password, verify_password
from app.utils.datetime import utc_now

BASE = "/api/v1/auth/pin"
MOBILE = "9000000077"


@pytest.fixture
async def pin_account(mock_db, monkeypatch):
    user = User(
        mobile=MOBILE,
        role="customer",
        status="active",
        password_hash=hash_password("OriginalPass1!"),
    )
    uid = (
        await mock_db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    ).inserted_id
    await mock_db.integration_configs.insert_one(
        {
            "provider": "airtel_iq",
            "integration_type": "sms",
            "is_enabled": True,
            "is_active": True,
            "is_deleted": False,
            "config_encrypted": encrypt(json.dumps(DEFAULTS)),
        }
    )
    monkeypatch.setattr(pin_service.secrets, "randbelow", lambda n: 8621)
    sent = []

    async def send(db, config, mobile, otp, reference):
        sent.append((mobile, otp, reference))
        return {"success": True, "status": "accepted", "error": None}

    monkeypatch.setattr(pin_service, "submit", send)
    return uid, sent


async def authorize(client, sent, purpose="FIRST_TIME_LOGIN"):
    started = await client.post(
        BASE + "/start", json={"mobile": MOBILE, "purpose": purpose}
    )
    assert started.status_code == 200, started.text
    data = started.json()["data"]
    otp = sent[-1][1]
    assert "otp" not in data and "dev_otp" not in data
    proof = await client.post(
        BASE + "/verify",
        json={
            "mobile": MOBILE,
            "purpose": purpose,
            "challenge_id": data["challenge_id"],
            "otp": otp,
        },
    )
    assert proof.status_code == 200, proof.text
    assert "access_token" not in proof.text
    return proof.json()["data"]["authorization"], data, otp


async def enroll(client, sent):
    proof, _, _ = await authorize(client, sent)
    r = await client.post(
        BASE + "/complete",
        json={"authorization": proof, "pin": "0472", "confirm_pin": "0472"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_enroll_login_refresh_reset_revokes_every_session(
    client, mock_db, pin_account
):
    uid, sent = pin_account
    first = await enroll(client, sent)
    row = await mock_db.users.find_one({"_id": uid})
    assert row["pin_hash"] != "0472" and verify_password("0472", row["pin_hash"])
    assert row["is_mobile_verified"] and row["pin_epoch"] == 1
    headers = {"Authorization": "Bearer " + first["access_token"]}
    assert (
        await client.get("/api/v1/auth/profile", headers=headers)
    ).status_code == 200
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert (await mock_db.sessions.find_one({"status": "active"}))["auth_epoch"] == 1
    normal = await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    assert normal.status_code == 200, normal.text
    assert len(sent) == 1  # Normal login never sends OTP.
    password = await client.post(
        "/api/v1/auth/login", json={"mobile": MOBILE, "password": "OriginalPass1!"}
    )
    assert password.status_code == 401
    proof, _, _ = await authorize(client, sent, "FORGOT_PIN")
    reset = await client.post(
        BASE + "/complete",
        json={"authorization": proof, "pin": "5938", "confirm_pin": "5938"},
    )
    assert reset.status_code == 200 and "access_token" not in reset.text
    assert (
        await client.get("/api/v1/auth/profile", headers=headers)
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refreshed.json()["data"]["refresh_token"]},
        )
    ).status_code == 401
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    ).status_code == 401
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "5938"})
    ).status_code == 200
    assert (
        await client.post(
            BASE + "/complete",
            json={"authorization": proof, "pin": "1111", "confirm_pin": "1111"},
        )
    ).status_code == 401
    audit = str(await mock_db.audit_logs.find().to_list(None))
    assert "0472" not in audit and "5938" not in audit


async def test_purpose_expiry_resend_and_attempt_exhaustion(
    client, mock_db, pin_account
):
    _, sent = pin_account
    started = await client.post(
        BASE + "/start", json={"mobile": MOBILE, "purpose": "FIRST_TIME_LOGIN"}
    )
    challenge = started.json()["data"]["challenge_id"]
    body = {
        "mobile": MOBILE,
        "purpose": "FIRST_TIME_LOGIN",
        "challenge_id": challenge,
        "otp": sent[-1][1],
    }
    assert (
        await client.post(
            BASE + "/start", json={"mobile": MOBILE, "purpose": "FIRST_TIME_LOGIN"}
        )
    ).status_code == 429
    assert (
        await client.post(BASE + "/verify", json=body | {"purpose": "FORGOT_PIN"})
    ).status_code == 422
    wrong = "0000" if sent[-1][1] != "0000" else "0001"
    for _ in range(5):
        assert (
            await client.post(BASE + "/verify", json=body | {"otp": wrong})
        ).status_code == 422
    assert (await client.post(BASE + "/verify", json=body)).status_code == 422
    await mock_db.auth_pin_challenges.update_many(
        {}, {"$set": {"next_send_at": utc_now() - timedelta(seconds=1)}}
    )
    new = await client.post(
        BASE + "/start", json={"mobile": MOBILE, "purpose": "FIRST_TIME_LOGIN"}
    )
    assert new.status_code == 200
    assert (await client.post(BASE + "/verify", json=body)).status_code == 422
    await mock_db.auth_pin_challenges.update_many(
        {}, {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}}
    )
    assert (
        await client.post(
            BASE + "/verify",
            json=body
            | {"challenge_id": new.json()["data"]["challenge_id"], "otp": sent[-1][1]},
        )
    ).status_code == 422


async def test_concurrent_proof_and_complete_are_single_use(
    client, mock_db, pin_account
):
    _, sent = pin_account
    started = (
        await client.post(
            BASE + "/start", json={"mobile": MOBILE, "purpose": "FIRST_TIME_LOGIN"}
        )
    ).json()["data"]
    body = {
        "mobile": MOBILE,
        "purpose": "FIRST_TIME_LOGIN",
        "challenge_id": started["challenge_id"],
        "otp": sent[-1][1],
    }
    results = await asyncio.gather(
        *(client.post(BASE + "/verify", json=body) for _ in range(2))
    )
    assert sorted(r.status_code for r in results) == [200, 422]
    proof = next(
        r.json()["data"]["authorization"] for r in results if r.status_code == 200
    )
    results = await asyncio.gather(
        *(
            client.post(
                BASE + "/complete",
                json={"authorization": proof, "pin": "1234", "confirm_pin": "1234"},
            )
            for _ in range(2)
        )
    )
    assert sum(r.status_code == 200 for r in results) == 1
    assert await mock_db.sessions.count_documents({"status": "active"}) == 1


async def test_lockout_and_expired_lock_recovery(client, mock_db, pin_account):
    uid, sent = pin_account
    await enroll(client, sent)
    for _ in range(5):
        assert (
            await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "9999"})
        ).status_code == 401
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    ).status_code == 401
    await mock_db.users.update_one(
        {"_id": uid}, {"$set": {"pin_locked_until": utc_now() - timedelta(seconds=1)}}
    )
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    ).status_code == 200


async def test_unknown_account_no_sms_and_validation_no_secret_echo(
    client, pin_account
):
    _, sent = pin_account
    result = await client.post(
        BASE + "/start", json={"mobile": "9000000088", "purpose": "FORGOT_PIN"}
    )
    assert result.status_code == 200 and not sent
    assert "eligible" in result.json()["data"]["message"]
    for bad in ["12345", "abcd", "１２３４"]:
        result = await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": bad})
        assert result.status_code == 422 and bad not in result.text


async def test_proof_expiry_and_mismatch_do_not_mutate_account(
    client, mock_db, pin_account
):
    uid, sent = pin_account
    proof, _, _ = await authorize(client, sent)
    assert (
        await client.post(
            BASE + "/complete",
            json={"authorization": proof, "pin": "1234", "confirm_pin": "5678"},
        )
    ).status_code == 422
    await mock_db.auth_pin_challenges.update_many(
        {}, {"$set": {"authorization_expires_at": utc_now() - timedelta(seconds=1)}}
    )
    assert (
        await client.post(
            BASE + "/complete",
            json={"authorization": proof, "pin": "1234", "confirm_pin": "1234"},
        )
    ).status_code == 401
    assert not (await mock_db.users.find_one({"_id": uid}))["pin_hash"]


async def test_otp_cannot_be_chosen_as_pin(client, pin_account):
    _, sent = pin_account
    proof, _, otp = await authorize(client, sent)
    r = await client.post(
        BASE + "/complete",
        json={"authorization": proof, "pin": otp, "confirm_pin": otp},
    )
    assert r.status_code == 422
    assert (
        await client.post(
            BASE + "/complete",
            json={"authorization": proof, "pin": "0472", "confirm_pin": "0472"},
        )
    ).status_code == 200


async def test_disabled_unenrolled_accounts_and_rate_limits(
    client, mock_db, pin_account
):
    uid, sent = pin_account
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    ).status_code == 401
    await enroll(client, sent)
    await mock_db.users.update_one({"_id": uid}, {"$set": {"status": "disabled"}})
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "0472"})
    ).status_code == 401
    for _ in range(8):
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "9999"})
    assert (
        await client.post(BASE + "/login", json={"mobile": MOBILE, "pin": "9999"})
    ).status_code == 429


async def test_owner_cutover_requires_enrollment_and_ready_provider(
    client, mock_db, owner_headers, pin_account
):
    _, sent = pin_account
    assert (
        await client.post(BASE + "/cutover", headers=owner_headers)
    ).status_code == 409
    await enroll(client, sent)
    assert (
        await client.post(BASE + "/cutover", headers=owner_headers)
    ).status_code == 409
    await mock_db.integration_configs.update_many(
        {}, {"$set": {"last_success_at": utc_now()}}
    )
    assert (
        await client.post(BASE + "/cutover", headers=owner_headers)
    ).status_code == 200
    assert (await client.get(BASE + "/policy")).json()["data"]["mode"] == "pin_only"
    # Even a newly provisioned account without a PIN cannot fall back after cutover.
    user = User(
        mobile="9000000066",
        role="customer",
        status="active",
        password_hash=hash_password("OriginalPass1!"),
    )
    await mock_db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"mobile": user.mobile, "password": "OriginalPass1!"},
        )
    ).status_code == 401


async def test_non_owner_cannot_cut_over(client, employee_headers):
    assert (
        await client.post(BASE + "/cutover", headers=employee_headers)
    ).status_code == 403


@pytest.mark.parametrize("role", ["owner", "employee", "referral_partner"])
async def test_internal_roles_keep_password_and_cannot_use_pin(
    client, mock_db, pin_account, role
):
    _, sent = pin_account
    mobile = "9000000055"
    user = User(
        mobile=mobile,
        role=role,
        status="active",
        password_hash=hash_password("StaffPass1!"),
        pin_hash=hash_password("0472"),
    )
    uid = (
        await mock_db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    ).inserted_id
    await mock_db.auth_login_policy.update_one(
        {"_id": "default"}, {"$set": {"mode": "pin_only"}}, upsert=True
    )
    normal = await client.post(
        "/api/v1/auth/login", json={"mobile": mobile, "password": "StaffPass1!"}
    )
    assert normal.status_code == 200, normal.text
    assert (
        await client.post(BASE + "/login", json={"mobile": mobile, "pin": "0472"})
    ).status_code == 401
    for purpose in ["FIRST_TIME_LOGIN", "FORGOT_PIN"]:
        r = await client.post(
            BASE + "/start", json={"mobile": mobile, "purpose": purpose}
        )
        assert r.status_code == 200  # Generic response; no role/account disclosure.
    assert not sent
    assert (await mock_db.users.find_one({"_id": uid}))["failed_pin_attempts"] == 0


async def test_role_change_invalidates_existing_customer_setup_proof(
    client, mock_db, pin_account
):
    uid, sent = pin_account
    proof, _, _ = await authorize(client, sent)
    await mock_db.users.update_one({"_id": uid}, {"$set": {"role": "employee"}})
    result = await client.post(
        BASE + "/complete",
        json={"authorization": proof, "pin": "0472", "confirm_pin": "0472"},
    )
    assert result.status_code == 401
    assert not (await mock_db.users.find_one({"_id": uid}))["pin_hash"]
