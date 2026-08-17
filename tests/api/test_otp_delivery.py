"""Tests for `AuthService._deliver_otp` / `_active_sms_config` (Module 1, previously
frozen) — wiring login/signup/forgot-password OTP delivery to the already-real,
already-tested MSG91 `send_sms` adapter (`communication/adapters.py`, see
tests/api/test_msg91.py) instead of the `NotConfiguredSmsClient` stub.

Redis-backed OTP generation/hashing/verification (`otp_service.py`) is completely
unchanged by this — these tests only cover the delivery step, and confirm the
Redis OTP flow still works end-to-end regardless of whether an SMS provider is
configured. No real MSG91 account/credentials exist in this environment; every
network call is monkeypatched at `_send_msg91_request`, matching test_msg91.py's own
established pattern.
"""

import json
import logging

import pytest

from app.features.auth import service as auth_service_module
from app.features.auth.service import AuthService
from app.features.communication import adapters as communication_adapters
from app.features.integrations.models import IntegrationConfig
from app.security.encryption import encrypt

MOBILE = "9876543210"


class _ProductionSettings:
    otp_mode = "production"


def _use_production_otp_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: _ProductionSettings())


async def _seed_sms_config(mock_db, *, provider: str = "msg91", is_active: bool = True, **extra: str) -> None:
    config_values = {"auth_key": "super-secret-authkey", "sender_id": "AFSCRM", "flow_id": "flow-generic"}
    config_values.update(extra)
    config = IntegrationConfig(
        integration_code="AFS-INTG-SMS", integration_type="sms", provider=provider, name="MSG91 SMS",
        config_encrypted=encrypt(json.dumps(config_values)), is_enabled=True, is_active=is_active,
    )
    await mock_db["integration_configs"].insert_one(config.model_dump(by_alias=True, exclude={"id"}))


# ---------------------------------------------------------------------- development mode (unchanged)


async def test_dev_mode_never_calls_send_sms(mock_db, mock_redis, monkeypatch):
    called = False

    async def _fail_if_called(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(auth_service_module, "send_sms", _fail_if_called)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "123456")

    assert called is False


# ---------------------------------------------------------------------- production mode, no provider configured


async def test_production_mode_no_active_config_does_not_raise(mock_db, mock_redis, monkeypatch):
    _use_production_otp_mode(monkeypatch)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "123456")  # must not raise — signup/login still succeeds


# ---------------------------------------------------------------------- production mode, MSG91 configured


async def test_production_mode_sends_via_msg91_with_otp_variable(mock_db, mock_redis, monkeypatch):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db)
    captured = {}

    async def _fake_request(url, *, auth_key, json_body):
        captured["auth_key"] = auth_key
        captured["json_body"] = json_body
        return True, {"type": "success", "message": "req-1"}, 200, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "654321")

    assert captured["json_body"]["flow_id"] == "flow-generic"
    assert captured["json_body"]["recipients"][0]["mobiles"] == "919876543210"
    assert captured["json_body"]["recipients"][0]["VAR1"] == "654321"
    assert captured["auth_key"] == "super-secret-authkey"


async def test_otp_flow_id_overrides_generic_flow_id_for_msg91(mock_db, mock_redis, monkeypatch):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db, otp_flow_id="flow-otp-specific")
    captured = {}

    async def _fake_request(url, *, auth_key, json_body):
        captured["json_body"] = json_body
        return True, {"type": "success", "message": "req-1"}, 200, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "111222")

    assert captured["json_body"]["flow_id"] == "flow-otp-specific"


async def test_non_msg91_provider_uses_generic_send_sms_path(mock_db, mock_redis, monkeypatch):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db, provider="generic_http", api_url="https://sms.example/send", api_key="k1")
    called = {}

    async def _fake_timed_post(url, **kwargs):
        called["url"] = url
        return True, None, 5

    monkeypatch.setattr(communication_adapters, "_timed_post", _fake_timed_post)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "333444")

    assert called["url"] == "https://sms.example/send"


# ---------------------------------------------------------------------- delivery failures never break login/signup


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "invalid authkey"),
        (429, "rate limit exceeded"),
        (500, "internal error"),
    ],
)
async def test_msg91_failure_does_not_raise(mock_db, mock_redis, monkeypatch, status_code, message):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db)

    async def _fake_request(url, *, auth_key, json_body):
        return status_code < 400, {"type": "error", "message": message}, status_code, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)
    service = AuthService(mock_db, mock_redis)

    await service._deliver_otp(MOBILE, "555666")  # must not raise


async def test_msg91_timeout_does_not_raise(mock_db, mock_redis, monkeypatch):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db)

    async def _raise_timeout(url, *, auth_key, json_body):
        import httpx

        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _raise_timeout)
    service = AuthService(mock_db, mock_redis)

    # _send_msg91_sms catches httpx.HTTPError (TimeoutException's own base class) around
    # the request and returns a failed DeliveryOutcome instead of propagating — signup/
    # login must keep succeeding even if MSG91 itself is unreachable.
    await service._deliver_otp(MOBILE, "777888")


# ---------------------------------------------------------------------- secrets never logged


async def test_authkey_never_logged_on_success(mock_db, mock_redis, monkeypatch, caplog):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db)

    async def _fake_request(url, *, auth_key, json_body):
        return True, {"type": "success", "message": "req-1"}, 200, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)
    service = AuthService(mock_db, mock_redis)

    with caplog.at_level(logging.DEBUG):
        await service._deliver_otp(MOBILE, "999000")

    assert "super-secret-authkey" not in caplog.text


async def test_authkey_never_logged_on_failure(mock_db, mock_redis, monkeypatch, caplog):
    _use_production_otp_mode(monkeypatch)
    await _seed_sms_config(mock_db)

    async def _fake_request(url, *, auth_key, json_body):
        return False, {"type": "error", "message": "bad request"}, 400, 10

    monkeypatch.setattr(communication_adapters, "_send_msg91_request", _fake_request)
    service = AuthService(mock_db, mock_redis)

    with caplog.at_level(logging.DEBUG):
        await service._deliver_otp(MOBILE, "121212")

    assert "super-secret-authkey" not in caplog.text
    assert "121212" not in caplog.text  # the OTP itself must never be logged either


# ---------------------------------------------------------------------- Redis OTP flow unaffected (regression guard)


async def test_signup_otp_flow_still_works_without_any_sms_provider_configured(client, owner_headers):
    """End-to-end regression guard: with no active SMS IntegrationConfig at all (this
    test's default db state) and default (development) otp_mode, send-otp/verify-otp
    must behave exactly as before this change — dev_otp still returned, still verifiable.
    """
    r = await client.post(
        "/api/v1/auth/send-otp", json={"mobile": "9876500001", "role": "customer"}, headers=owner_headers
    )
    assert r.status_code == 200, r.text
    otp = r.json()["data"]["dev_otp"]
    assert otp is not None

    r = await client.post(
        "/api/v1/auth/verify-otp", json={"mobile": "9876500001", "otp": otp, "purpose": "signup"}
    )
    assert r.status_code == 200, r.text
