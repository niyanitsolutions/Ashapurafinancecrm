"""End-to-end API tests for the Authentication module, run against mongomock + fakeredis
(see conftest.py) so they need no live Docker services. Exercises every one of the 9
fixed endpoints, invitation-only signup authorization, and refresh-token family/reuse
detection (see docs/AUTHENTICATION.md).
"""

CUSTOMER_MOBILE = "9876543210"
REFERRAL_MOBILE = "9876543299"


async def _invite(client, headers, mobile: str, role: str) -> str:
    r = await client.post("/api/v1/auth/send-otp", json={"mobile": mobile, "role": role}, headers=headers)
    assert r.status_code == 200, r.text
    otp = r.json()["data"]["dev_otp"]
    assert otp is not None
    return otp


async def _complete_signup(client, mobile: str, otp: str, password: str, purpose: str = "signup") -> dict:
    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": otp, "purpose": purpose})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    ticket = body["otp_verified_token"]

    r = await client.post(
        "/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": password}
    )
    assert r.status_code == 200, r.text
    return body


async def _signup_customer(client, owner_headers, mobile: str = CUSTOMER_MOBILE, password: str = "SuperSecret1") -> None:
    otp = await _invite(client, owner_headers, mobile, "customer")
    body = await _complete_signup(client, mobile, otp, password)
    assert body["is_new_user"] is True


async def _login(client, mobile: str, password: str) -> dict:
    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_full_customer_signup_login_profile_refresh_logout(client, owner_headers):
    await _signup_customer(client, owner_headers)
    tokens = await _login(client, CUSTOMER_MOBILE, "SuperSecret1")
    assert tokens["role"] == "customer"
    access_token = tokens["access_token"]

    r = await client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200, r.text
    profile = r.json()["data"]
    assert profile["mobile"] == CUSTOMER_MOBILE
    assert profile["role"] == "customer"
    assert profile["status"] == "active"

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    new_tokens = r.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    r = await client.get(
        "/api/v1/auth/profile", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 401, r.text


async def test_send_otp_requires_auth(client):
    r = await client.post("/api/v1/auth/send-otp", json={"mobile": CUSTOMER_MOBILE, "role": "customer"})
    assert r.status_code == 401, r.text


async def test_send_otp_rejects_invalid_role(client, owner_headers):
    r = await client.post(
        "/api/v1/auth/send-otp", json={"mobile": "9876500000", "role": "owner"}, headers=owner_headers
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "invalid_role_for_signup"


async def test_employee_can_invite_customer_but_not_referral_partner(client, employee_headers):
    r = await client.post(
        "/api/v1/auth/send-otp", json={"mobile": CUSTOMER_MOBILE, "role": "customer"}, headers=employee_headers
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/auth/send-otp",
        json={"mobile": REFERRAL_MOBILE, "role": "referral_partner"},
        headers=employee_headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


async def test_owner_can_invite_referral_partner(client, owner_headers):
    otp = await _invite(client, owner_headers, REFERRAL_MOBILE, "referral_partner")
    body = await _complete_signup(client, REFERRAL_MOBILE, otp, "PartnerPass1")
    assert body["is_new_user"] is True
    tokens = await _login(client, REFERRAL_MOBILE, "PartnerPass1")
    assert tokens["role"] == "referral_partner"


async def test_send_otp_already_registered(client, owner_headers):
    await _signup_customer(client, owner_headers)
    r = await client.post(
        "/api/v1/auth/send-otp", json={"mobile": CUSTOMER_MOBILE, "role": "customer"}, headers=owner_headers
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "already_registered"


async def test_verify_otp_wrong_code_then_max_attempts(client, owner_headers):
    mobile = "9876543211"
    await _invite(client, owner_headers, mobile, "customer")

    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": "000000", "purpose": "signup"}
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "otp_mismatch"

    r = await client.post(
        "/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": "000000", "purpose": "signup"}
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "otp_max_attempts_exceeded"


async def test_verify_otp_never_sent(client):
    r = await client.post(
        "/api/v1/auth/verify-otp",
        json={"mobile": "9999999999", "otp": "123456", "purpose": "signup"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "otp_not_found"


async def test_login_invalid_credentials(client, owner_headers):
    await _signup_customer(client, owner_headers)
    r = await client.post(
        "/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "WrongPassword1"}
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "invalid_credentials"


async def test_login_lockout_after_max_attempts(client, owner_headers):
    await _signup_customer(client, owner_headers)
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "WrongPassword1"}
        )
        assert r.status_code == 401

    r = await client.post(
        "/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "SuperSecret1"}
    )
    assert r.status_code == 423, r.text
    assert r.json()["error"]["code"] == "account_locked"


async def test_forgot_password_flow_changes_password(client, owner_headers):
    await _signup_customer(client, owner_headers)

    r = await client.post("/api/v1/auth/forgot-password", json={"mobile": CUSTOMER_MOBILE})
    assert r.status_code == 200, r.text
    otp = r.json()["data"]["dev_otp"]
    assert otp is not None

    r = await client.post(
        "/api/v1/auth/verify-otp",
        json={"mobile": CUSTOMER_MOBILE, "otp": otp, "purpose": "forgot_password"},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["is_new_user"] is False
    ticket = body["otp_verified_token"]

    r = await client.post(
        "/api/v1/auth/reset-password",
        json={"otp_verified_token": ticket, "new_password": "BrandNewPass1"},
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "SuperSecret1"}
    )
    assert r.status_code == 401
    tokens = await _login(client, CUSTOMER_MOBILE, "BrandNewPass1")
    assert tokens["role"] == "customer"


async def test_forgot_password_unknown_mobile_is_silent(client):
    r = await client.post("/api/v1/auth/forgot-password", json={"mobile": "9111111111"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["dev_otp"] is None


async def test_reset_password_ticket_is_single_use(client, owner_headers):
    otp = await _invite(client, owner_headers, REFERRAL_MOBILE, "referral_partner")
    r = await client.post(
        "/api/v1/auth/verify-otp",
        json={"mobile": REFERRAL_MOBILE, "otp": otp, "purpose": "signup"},
    )
    ticket = r.json()["data"]["otp_verified_token"]

    r = await client.post(
        "/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": "FirstPass1"}
    )
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": "SecondPass1"}
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "invalid_or_expired_ticket"


async def test_change_password_requires_auth(client):
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "a", "new_password": "SuperSecret2"},
    )
    assert r.status_code == 401


async def test_change_password_success(client, owner_headers):
    await _signup_customer(client, owner_headers)
    tokens = await _login(client, CUSTOMER_MOBILE, "SuperSecret1")

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "SuperSecret1", "new_password": "SuperSecret2"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "SuperSecret1"}
    )
    assert r.status_code == 401
    await _login(client, CUSTOMER_MOBILE, "SuperSecret2")


async def test_profile_requires_auth(client):
    r = await client.get("/api/v1/auth/profile")
    assert r.status_code == 401


async def test_audit_logs_are_written_for_key_events(client, mock_db, owner_headers):
    await _signup_customer(client, owner_headers)
    await _login(client, CUSTOMER_MOBILE, "SuperSecret1")
    await client.post("/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "wrong"})

    events = {doc["event_type"] async for doc in mock_db["audit_logs"].find({})}
    assert {"otp_sent", "otp_verified", "password_reset", "login", "failed_login"} <= events


async def test_failed_login_audit_log_captures_reason(client, mock_db, owner_headers):
    await _signup_customer(client, owner_headers)

    await client.post("/api/v1/auth/login", json={"mobile": CUSTOMER_MOBILE, "password": "wrong"})
    entry = await mock_db["audit_logs"].find_one({"event_type": "failed_login", "mobile": CUSTOMER_MOBILE})
    assert entry["metadata"]["reason"] == "invalid_password"

    await client.post("/api/v1/auth/login", json={"mobile": "9000000099", "password": "whatever1"})
    entry = await mock_db["audit_logs"].find_one({"event_type": "failed_login", "mobile": "9000000099"})
    assert entry["metadata"]["reason"] == "account_not_found"


async def test_session_captures_login_history_fields(client, mock_db, owner_headers):
    await _signup_customer(client, owner_headers)
    await _login(client, CUSTOMER_MOBILE, "SuperSecret1")

    session = await mock_db["sessions"].find_one({"user_id": {"$exists": True}}, sort=[("login_at", -1)])
    assert session is not None
    assert session["status"] == "active"
    assert session["browser"] is not None
    assert session["operating_system"] is not None
    assert session["device"] is not None
    assert session["token_id"] is not None
    assert session["family_id"] is not None
    assert session["login_method"] == "password"
    assert session["login_at"] is not None
    assert session["last_activity_at"] is not None
    # geoip is an unconfigured stub this module — see docs/KNOWN_LIMITATIONS.md
    assert session["city"] is None
    assert session["country"] is None


async def test_refresh_reuse_revokes_entire_family(client, mock_db, owner_headers):
    await _signup_customer(client, owner_headers)
    tokens = await _login(client, CUSTOMER_MOBILE, "SuperSecret1")

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    new_tokens = r.json()["data"]

    # reusing the now-stale (rotated-out) original refresh token is treated as theft
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "invalid_refresh_token"

    # the entire family is revoked as a result — even the legitimately-rotated new token is dead now
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 401, r.text

    events = {doc["event_type"] async for doc in mock_db["audit_logs"].find({})}
    assert "suspicious_refresh_reuse" in events
