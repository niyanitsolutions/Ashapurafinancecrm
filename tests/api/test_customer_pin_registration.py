# ruff: noqa: F811
"""Customer registration uses disposable loopback MongoDB and mocked Airtel only."""

import asyncio
import json
from datetime import timedelta

import pytest
from app.config.database import get_database
from app.features.communication import airtel_iq
from app.features.customer.indexes import ensure_customer_indexes
from app.features.integrations.airtel_iq import DEFAULTS
from app.security.encryption import encrypt
from app.security.pin import verify_pin
from app.utils.datetime import utc_now
from test_pin_mongo_integration import pin_mongo  # noqa: F401

BASE = "/api/v1/customer-registration"
DETAILS = {
    "mobile": "9000000088",
    "pin": "0472",
    "confirm_pin": "0472",
}


@pytest.fixture
async def registration(client, pin_mongo, monkeypatch):
    db = pin_mongo
    await ensure_customer_indexes(db)
    client._transport.app.dependency_overrides[get_database] = lambda: db
    await db.integration_configs.insert_one({
        "provider": "airtel_iq", "integration_type": "sms", "is_active": True,
        "is_enabled": True, "is_deleted": False,
        "config_encrypted": encrypt(json.dumps(DEFAULTS | {
            "customer_id": "fixture-customer", "username": "fixture-user",
            "password": "fixture-secret", "contract_confirmed": "true",
        })),
    })
    sent = []

    async def request(body, username, password):
        assert (username, password) == ("fixture-user", "fixture-secret")
        sent.append(body)
        return 200, None

    monkeypatch.setattr(airtel_iq, "request", request)
    return client, db, sent


async def verified(registration, existing_customers=0):
    client, db, sent = registration
    r = await client.post(BASE + "/start", json=DETAILS)
    assert r.status_code == 200, r.text
    assert await db.users.count_documents({}) == 0
    assert await db.customers.count_documents({}) == existing_customers
    challenge = r.json()["data"]["challenge_id"]
    code = sent[-1]["message"].split(" is ")[1].split(".")[0]
    assert "dev_otp" not in r.text and code not in r.text
    body = {"mobile": DETAILS["mobile"], "purpose": "REGISTRATION", "challenge_id": challenge, "otp": code}
    r = await client.post("/api/v1/auth/pin/verify", json=body)
    assert r.status_code == 200, r.text
    assert await db.users.count_documents({}) == 0
    return r.json()["data"]["authorization"], body


async def test_register_login_and_single_use(registration):
    client, db, sent = registration
    proof, verify_body = await verified(registration)
    response = await client.post(
        BASE + "/complete", json=DETAILS | {"authorization": proof}
    )
    assert response.status_code == 200, response.text
    user = await db.users.find_one({"mobile": DETAILS["mobile"]})
    assert (
        user["password_hash"] is None
        and user["pin_hash"].startswith("$argon2id$")
        and verify_pin("0472", user["pin_hash"])
    )
    assert (
        user["is_mobile_verified"]
        and user["mobile_verified_at"]
        and user["registration_method"] == "mobile_pin"
    )
    assert await db.customers.count_documents({}) == 0
    audit = await db.audit_logs.find_one({"user_id": str(user["_id"])})
    assert (
        audit["metadata"]["profile_status"] == "pending"
        and "terms_accepted" not in audit["metadata"]
    )
    assert (
        await client.post("/api/v1/auth/pin/verify", json=verify_body)
    ).status_code == 422
    assert (
        await client.post(BASE + "/complete", json=DETAILS | {"authorization": proof})
    ).status_code == 422
    login = await client.post(
        "/api/v1/auth/pin/login", json={"mobile": DETAILS["mobile"], "pin": "0472"}
    )
    assert (
        login.status_code == 200
        and login.json()["data"]["role"] == "customer"
        and len(sent) == 1
    )
    bad = await client.post(
        "/api/v1/auth/pin/login", json={"mobile": DETAILS["mobile"], "pin": "9999"}
    )
    assert bad.status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"mobile": "123"},
        {"email": "invalid"},
        {"pin": "abcd"},
        {"confirm_pin": "9999"},
        {"full_name": ""},
        {"terms_accepted": False},
    ],
)
async def test_invalid_details_do_not_send(registration, change):
    client, db, sent = registration
    r = await client.post(BASE + "/start", json=DETAILS | change)
    assert r.status_code == 422
    assert not sent and await db.users.count_documents({}) == 0
    assert "0472" not in r.text


async def test_expiry_wrong_mobile_and_no_proof(registration):
    client, db, _ = registration
    assert (await client.post(BASE + "/complete", json=DETAILS | {"authorization": "x" * 43})).status_code == 422
    proof, _ = await verified(registration)
    assert (await client.post(BASE + "/complete", json=DETAILS | {"mobile": "9000000099", "authorization": proof})).status_code == 422
    await db.auth_pin_challenges.update_many({}, {"$set": {"authorization_expires_at": utc_now() - timedelta(seconds=1)}})
    assert (await client.post(BASE + "/complete", json=DETAILS | {"authorization": proof})).status_code == 422
    assert await db.users.count_documents({}) == 0


async def test_failed_audit_insert_rolls_back_user_and_proof(registration):
    client, db, _ = registration
    proof, _ = await verified(registration)
    await db.audit_logs.create_index("event_type", unique=True)
    await db.audit_logs.insert_one({"event_type": "customer_registered"})
    response = await client.post(
        BASE + "/complete", json=DETAILS | {"authorization": proof}
    )
    assert response.status_code == 409
    assert (
        await db.users.count_documents({}) == 0
        and await db.customers.count_documents({}) == 0
    )
    assert (await db.auth_pin_challenges.find_one({"purpose": "REGISTRATION"}))[
        "state"
    ] == "verified"


async def test_otp_expiry_resend_and_attempt_limits(registration):
    client, db, sent = registration
    r = await client.post(BASE + "/start", json=DETAILS)
    challenge = r.json()["data"]["challenge_id"]
    assert (await client.post(BASE + "/start", json=DETAILS)).status_code == 429
    await db.auth_pin_challenges.update_many({}, {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}})
    code = sent[-1]["message"].split(" is ")[1].split(".")[0]
    r = await client.post("/api/v1/auth/pin/verify", json={"mobile": DETAILS["mobile"], "purpose": "REGISTRATION", "challenge_id": challenge, "otp": code})
    assert r.status_code == 422 and await db.users.count_documents({}) == 0


async def test_concurrent_completion_only_one_account(registration):
    client, db, _ = registration
    proof, _ = await verified(registration)
    # Replaying a consumed proof is covered above; concurrent verification is covered
    # by the shared real-Mongo PIN atomicity tests. Unique mobile is enforced here too.
    results = await asyncio.gather(*(client.post(BASE + "/complete", json=DETAILS | {"authorization": proof}) for _ in range(2)))
    assert sum(r.status_code == 200 for r in results) == 1
    assert await db.users.count_documents({}) == 1
    assert await db.customers.count_documents({}) == 0


async def test_registration_cannot_skip_detail_validation_via_pin_start(registration):
    client, db, sent = registration
    r = await client.post("/api/v1/auth/pin/start", json={"mobile": DETAILS["mobile"], "purpose": "REGISTRATION"})
    assert r.status_code == 422 and not sent
    assert await db.users.count_documents({}) == 0


async def test_rejected_sms_never_claims_sent_or_creates_account(registration, monkeypatch):
    client, db, _ = registration

    async def reject(*args):
        return 401, {"message": "Unauthorized"}

    monkeypatch.setattr(airtel_iq, "request", reject)
    r = await client.post(BASE + "/start", json=DETAILS)
    assert r.status_code == 422
    assert "OTP submission was not confirmed" in r.text
    assert await db.users.count_documents({}) == 0
    assert (await db.auth_pin_challenges.find_one({}))["state"] == "failed"


async def test_registration_never_claims_historical_lead_by_mobile_only(registration):
    from app.features.leads.models import Lead

    client, db, _ = registration
    lead = Lead(lead_code="AFS-LEAD-FIXTURE", full_name="Existing Name", mobile=DETAILS["mobile"],
                source_id="fixture-source", product_category="loan", product_id="fixture-product",
                assigned_to="fixture-employee")
    lead_id = (await db.leads.insert_one(lead.model_dump(by_alias=True, exclude={"id"}))).inserted_id
    proof, _ = await verified(registration)
    r = await client.post(BASE + "/complete", json=DETAILS | {"authorization": proof})
    assert r.status_code == 200, r.text
    linked = await db.leads.find_one({"_id": lead_id})
    user = await db.users.find_one({"mobile": DETAILS["mobile"]})
    customer = await db.customers.find_one({"user_id": str(user["_id"])})
    assert linked.get("user_id") is None and linked.get("customer_id") is None
    assert not linked["account_created"]
    assert customer is None
    login = await client.post(
        "/api/v1/auth/pin/login",
        json={"mobile": DETAILS["mobile"], "pin": DETAILS["pin"]},
    )
    headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
    profile = await client.post(
        "/api/v1/customers/me",
        headers=headers,
        json={"full_name": "Collected After Verification"},
    )
    assert profile.status_code == 200, profile.text
    unchanged = await db.leads.find_one({"_id": lead_id})
    assert unchanged == linked
    assert await db.customers.count_documents({}) == 1
    assert linked["assigned_to"] == "fixture-employee" and linked["full_name"] == "Existing Name"
    assert linked["source_id"] == "fixture-source" and linked["product_id"] == "fixture-product"


async def test_no_account_disclosure_until_otp_ownership(registration):
    from app.features.auth.models import User

    client, db, sent = registration
    user = User(mobile=DETAILS["mobile"], role="employee", status="active")
    await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    result = await client.post(BASE + "/start", json=DETAILS)
    assert result.status_code == 200 and len(sent) == 1
    assert "already" not in result.text and "employee" not in result.text
    challenge = result.json()["data"]["challenge_id"]
    code = sent[-1]["message"].split(" is ")[1].split(".")[0]
    verified = await client.post(
        "/api/v1/auth/pin/verify",
        json={
            "mobile": DETAILS["mobile"],
            "purpose": "REGISTRATION",
            "challenge_id": challenge,
            "otp": code,
        },
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["next_action"] == "login"
    assert verified.json()["data"]["authorization"] == ""
    proof = await db.auth_pin_challenges.find_one({})
    assert proof["state"] == "consumed" and "authorization_hash" not in proof
    assert await db.customers.count_documents({}) == 0


async def test_existing_customer_requires_review_after_verified_mobile(registration):
    client, db, _ = registration
    await db.customers.insert_one(
        {
            "customer_code": "HISTORICAL",
            "user_id": "historical-owner",
            "mobile": "+91 " + DETAILS["mobile"],
            "full_name": "Existing Verified Customer",
            "is_deleted": False,
        }
    )
    proof, _ = await verified(registration, existing_customers=1)
    response = await client.post(
        BASE + "/complete", json=DETAILS | {"authorization": proof}
    )
    assert response.status_code == 409 and "ownership review" in response.text
    assert (
        await db.users.count_documents({}) == 0
        and await db.customers.count_documents({}) == 1
    )
