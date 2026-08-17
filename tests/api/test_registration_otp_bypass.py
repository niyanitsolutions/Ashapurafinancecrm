"""Tests for the TEMPORARY MSG91 DLT-approval customer self-registration OTP bypass
(`Settings.registration_otp_bypass`, `CustomerService.bypass_verify_registration_mobile`,
`POST /customer-registration/bypass-verify`). See
`CustomerService.start_direct_registration`'s own docstring notes and
`tests/api/test_customer.py` for the normal (non-bypass) registration flow this reuses
unmodified.

Gated by exactly one flag — no allowlist (see settings.py's own comment on why: the flag
itself is the temporary, administrator-controlled switch). When on, ANY valid mobile with
a pending registration can bypass; the mobile itself is never hardcoded anywhere in this
feature's code, and no OTP value (real or fake) is ever generated or stored for a
bypassed mobile.

Scope: customer self-registration ONLY. Login, forgot-password, and every other OTP
purpose never call any of this code and must be provably unaffected.
"""

import random

import pytest

from app.config.settings import Settings
from app.features.customer import service as customer_service_module


def _random_mobile() -> str:
    # Deliberately randomized per test run (never a fixed literal) to prove the bypass
    # imposes no allowlist of its own — any syntactically valid Indian mobile qualifies.
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


class _FakeSettings:
    def __init__(self, *, bypass: bool, frontend_base_url: str = "http://localhost:5173") -> None:
        self.registration_otp_bypass = bypass
        self.frontend_base_url = frontend_base_url


def _enable_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customer_service_module, "get_settings", lambda: _FakeSettings(bypass=True))


def _disable_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customer_service_module, "get_settings", lambda: _FakeSettings(bypass=False))


def _complete_payload(mobile: str, token: str) -> dict:
    return {
        "full_name": "Test Customer", "email": "test.customer@example.com", "mobile": mobile,
        "password": "SuperSecret1!", "address_line1": "1 Main St", "city": "Mumbai", "state": "MH",
        "pincode": "400001", "otp_verified_token": token,
    }


# ---------------------------------------------------------------------- Settings — flag-only, no allowlist


def test_settings_has_no_allowlist_field():
    assert "registration_otp_bypass_allowlist" not in Settings.model_fields
    assert not hasattr(Settings, "registration_otp_bypass_mobiles")


def test_settings_bypass_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("REGISTRATION_OTP_BYPASS", raising=False)
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
    monkeypatch.setenv("MONGO_DB_NAME", "afs_crm_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.registration_otp_bypass is False


def test_settings_bypass_flag_can_be_turned_on_alone(monkeypatch):
    """No allowlist required — the flag alone is sufficient, and construction must not
    raise (this used to require a non-empty allowlist; that requirement is gone)."""
    monkeypatch.setenv("REGISTRATION_OTP_BYPASS", "true")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
    monkeypatch.setenv("MONGO_DB_NAME", "afs_crm_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.registration_otp_bypass is True


# ---------------------------------------------------------------------- bypass = false (default): unchanged behavior


async def test_bypass_disabled_start_reports_unavailable(client, mock_db, owner_headers, monkeypatch):
    _disable_bypass(monkeypatch)
    mobile = _random_mobile()
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["bypass_available"] is False
    assert r.json()["data"]["dev_otp"] is not None  # otp_mode=development in tests — unchanged


async def test_bypass_disabled_bypass_verify_endpoint_rejects_everyone(client, mock_db, owner_headers, monkeypatch):
    _disable_bypass(monkeypatch)
    mobile = _random_mobile()
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 403, r.text
    assert "otp_verified_token" not in r.text


# ---------------------------------------------------------------------- bypass = true: ANY valid mobile works


async def test_bypass_enabled_any_random_mobile_full_flow(client, mock_db, owner_headers, monkeypatch):
    """The core new requirement: with no allowlist configured anywhere, a freshly
    randomized mobile (never seen before, never hardcoded) must be able to bypass."""
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()

    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["bypass_available"] is True
    assert r.json()["data"]["dev_otp"] is not None  # unrelated dev-mode field, untouched by this feature

    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    token = r.json()["data"]["otp_verified_token"]
    assert token

    r = await client.post("/api/v1/customer-registration/complete", json=_complete_payload(mobile, token))
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": "SuperSecret1!"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "customer"


async def test_bypass_enabled_second_independent_random_mobile_also_works(client, mock_db, owner_headers, monkeypatch):
    """Confirms there is no hidden fixed/first-mobile-only special case — a second,
    independently randomized mobile in the same run bypasses identically."""
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()
    r = await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    assert r.json()["data"]["bypass_available"] is True
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 200, r.text


async def test_bypass_verify_ticket_is_single_use(client, mock_db, owner_headers, monkeypatch):
    """The bypass produces the exact same one-time ticket real OTP verification does —
    a second `complete` with the same token must fail, same as the real flow."""
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()
    await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    token = r.json()["data"]["otp_verified_token"]

    r = await client.post("/api/v1/customer-registration/complete", json=_complete_payload(mobile, token))
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/customer-registration/complete", json=_complete_payload(mobile, token) | {"email": "second@example.com"}
    )
    assert r.status_code != 200, r.text


async def test_bypass_enabled_but_registration_already_completed_cannot_bypass_again(client, mock_db, owner_headers, monkeypatch):
    """A mobile whose registration already completed (status is ACTIVE, not
    pending-password) must not get a second verification ticket."""
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()
    await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    token = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/customer-registration/complete", json=_complete_payload(mobile, token))
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 404, r.text


async def test_bypass_enabled_mobile_without_pending_registration_rejected(client, mock_db, owner_headers, monkeypatch):
    """A mobile that never called /start at all (no pending user row) must be rejected —
    closes the "call bypass-verify directly, skipping the normal start step" gap."""
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 404, r.text


async def test_bypass_enabled_invalid_mobile_format_rejected(client, mock_db, owner_headers, monkeypatch):
    """Mobile format is validated by the same request schema (`DirectRegisterRequest`)
    every other registration endpoint already uses — no new/looser validation here."""
    _enable_bypass(monkeypatch)
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": "12345"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------- login / forgot-password unaffected


async def test_login_and_forgot_password_unaffected_by_bypass_flag(client, mock_db, owner_headers, monkeypatch):
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()

    # Owner-invited signup (a different code path entirely — AuthService.send_otp,
    # never touched by this feature) still works exactly as before.
    r = await client.post("/api/v1/auth/send-otp", json={"mobile": mobile, "role": "customer"}, headers=owner_headers)
    assert r.status_code == 200, r.text
    otp = r.json()["data"]["dev_otp"]
    assert otp is not None

    r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": otp, "purpose": "signup"})
    assert r.status_code == 200, r.text
    ticket = r.json()["data"]["otp_verified_token"]
    r = await client.post("/api/v1/auth/reset-password", json={"otp_verified_token": ticket, "new_password": "SuperSecret1!"})
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/auth/login", json={"mobile": mobile, "password": "SuperSecret1!"})
    assert r.status_code == 200, r.text

    # Forgot-password for that now-active account is untouched too.
    r = await client.post("/api/v1/auth/forgot-password", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["dev_otp"] is not None


# ---------------------------------------------------------------------- audit + no secret/PII leakage


async def test_bypass_verify_writes_audit_log_with_mobile_and_purpose_only(client, mock_db, owner_headers, monkeypatch):
    _enable_bypass(monkeypatch)
    mobile = _random_mobile()
    await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 200, r.text

    entry = await mock_db["audit_logs"].find_one({"event_type": "registration_otp_bypassed", "mobile": mobile})
    assert entry is not None
    assert entry["metadata"] == {"purpose": "signup"}


async def test_bypass_rejection_response_contains_no_token_or_config_detail(client, mock_db, owner_headers, monkeypatch):
    _disable_bypass(monkeypatch)
    mobile = _random_mobile()
    await client.post("/api/v1/customer-registration/start", json={"mobile": mobile})
    r = await client.post("/api/v1/customer-registration/bypass-verify", json={"mobile": mobile})
    assert r.status_code == 403
    assert "otp_verified_token" not in r.text
    assert "REGISTRATION_OTP_BYPASS" not in r.text
