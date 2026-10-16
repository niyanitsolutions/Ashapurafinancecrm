import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError as SchemaError

from app.core.exceptions import ConflictError, ForbiddenError
from app.features.auth.models import User
from app.features.voice_assistant import native_adapter, native_service
from app.features.voice_assistant.native_config import NativeConfig, NativeConnectionInput, native_origin
from app.features.voice_assistant.native_service import NativeVoiceService, ensure_native_indexes
from app.features.voice_assistant.number_schemas import TelephoneNumberAction, TelephoneNumberInput
from app.security.encryption import decrypt
from app.utils.datetime import utc_now

BASE = "/api/v1/voice-assistant/native"
ORIGIN = "https://pbx.example.internal:8089"


@pytest.fixture
async def native_context(mock_db, owner_headers, monkeypatch):
    await ensure_native_indexes(mock_db)
    monkeypatch.setattr(native_service, "get_native_config", lambda: NativeConfig(allowed_origins=[ORIGIN]))
    actor = User.model_validate(await mock_db.users.find_one({"role": "owner"}))
    return NativeVoiceService(mock_db), actor


def connection_input(**kwargs):
    return NativeConnectionInput(name="Staging PBX", api_origin=ORIGIN, endpoint_name="approved-trunk", username="test-only-ari-user", password="test-only-ari-password", **kwargs)


def mock_ari(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(native_adapter.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))


async def test_registered_routes_are_owner_only(client, owner_headers, employee_headers, native_context):
    for endpoint in ("connections", "numbers"):
        assert (await client.get(f"{BASE}/{endpoint}")).status_code in (401, 403)
        assert (await client.get(f"{BASE}/{endpoint}", headers=employee_headers)).status_code == 403
        assert (await client.get(f"{BASE}/{endpoint}", headers=owner_headers)).status_code == 200


async def test_revocation_is_terminal_and_rotation_preserves_it(native_context):
    svc, actor = native_context
    connection = await svc.save_connection(connection_input(), actor)
    number = await svc.save_number(TelephoneNumberInput(number="+919000000901", label="Revocation test", connection_id=connection["id"]), actor)
    number = await svc.number_action(number["id"], TelephoneNumberAction(version=number["version"], action="revoke", reason="Authorization withdrawn"), actor)
    await svc.save_connection(connection_input(version=connection["version"]), actor, connection["id"])
    current = (await svc.numbers(actor))["items"][0]
    assert current["state"] == "revoked"
    with pytest.raises(ForbiddenError):
        await svc.number_action(number["id"], TelephoneNumberAction(version=current["version"], action="review", reason="Cannot bypass revocation"), actor)
    with pytest.raises(ForbiddenError):
        await svc.save_number(TelephoneNumberInput(version=current["version"], number=number["number"], label="Attempted restoration"), actor, number["id"])


async def test_credentials_encrypted_and_write_only(client, owner_headers, native_context, mock_db):
    response = await client.post(f"{BASE}/connections", headers=owner_headers, json={"name": "Staging PBX", "api_origin": ORIGIN, "endpoint_name": "approved-trunk", "username": "test-only-ari-user", "password": "test-only-ari-password"})
    assert response.status_code == 200, response.text
    item = response.json()["data"]
    assert item["credentials_configured"] is True and item["live_calling"] is False
    assert "test-only-ari" not in response.text
    stored = await mock_db.voice_native_connections.find_one({})
    assert json.loads(decrypt(stored["credentials_encrypted"]))["password"] == "test-only-ari-password"
    assert "test-only-ari-password" not in str(stored)
    assert "test-only-ari" not in str(await mock_db.audit_logs.find({}).to_list(None))


@pytest.mark.parametrize("origin", ["http://pbx.example.internal", "https://user:pass@pbx.example.internal", "https://pbx.example.internal/ari", "https://pbx.example.internal?token=bad", "https://169.254.169.254", "https://[fe80::1]", "https://0.0.0.0", "https://224.0.0.1"])
def test_unsafe_origins_rejected(origin):
    with pytest.raises(ValueError):
        native_origin(origin)


def test_loopback_and_normalized_origins():
    assert native_origin("https://PBX.example.internal:443/") == "https://pbx.example.internal"
    assert native_origin("http://[::1]:8088") == "http://[::1]:8088"
    with pytest.raises(SchemaError):
        connection_input(clear_credentials=True)


async def test_unallowlisted_configuration_never_sends_network(native_context, monkeypatch):
    svc, actor = native_context
    monkeypatch.setattr(native_service, "get_native_config", lambda: NativeConfig(allowed_origins=[]))
    connection = await svc.save_connection(connection_input(), actor)
    assert connection["state"] == "configuration_incomplete"
    async def forbidden(*args):
        pytest.fail("Unallowlisted settings must not reach the HTTP adapter")
    monkeypatch.setattr(native_adapter.AsteriskReadOnlyAdapter, "probe", forbidden)
    with pytest.raises(ForbiddenError):
        await svc.test_connection(connection["id"], actor)


async def test_real_http_probe_contract_and_no_calls(native_context, monkeypatch, mock_db):
    svc, actor = native_context
    requested = []
    def handler(request):
        requested.append((request.method, request.url.path))
        assert request.headers["authorization"].startswith("Basic ")
        assert not request.url.query
        data = {"ping": "pong"} if request.url.path.endswith("/ping") else {"technology": "PJSIP", "resource": "approved-trunk", "state": "online", "channel_ids": ["never-retain-channel"]}
        return httpx.Response(200, json=data)
    mock_ari(monkeypatch, handler)
    connection = await svc.save_connection(connection_input(), actor)
    result = await svc.test_connection(connection["id"], actor)
    assert requested == [("GET", "/ari/asterisk/ping"), ("GET", "/ari/endpoints/PJSIP/approved-trunk")]
    assert result["last_test"]["status"] == "control_probe_passed"
    assert result["last_test"]["media_verified"] is False
    assert result["last_test"]["calls_placed"] == 0
    assert "never-retain-channel" not in str(await mock_db.voice_native_tests.find({}).to_list(None))
    assert await mock_db.voice_calls.count_documents({}) == 0


@pytest.mark.parametrize("status,body,expected", [(401, {"secret": "must-not-leak"}, "credentials_or_read_permission_rejected"), (302, {}, "pbx_unexpected_status"), (429, {}, "pbx_rate_limited"), (200, {"ping": "wrong"}, "ari_ping_not_confirmed")])
async def test_probe_failures_are_safe(native_context, monkeypatch, status, body, expected):
    svc, actor = native_context
    mock_ari(monkeypatch, lambda request: httpx.Response(status, json=body, headers={"Location": "https://untrusted.example"}))
    item = await svc.save_connection(connection_input(), actor)
    result = await svc.test_connection(item["id"], actor)
    assert result["state"] == "verification_failed"
    assert result["last_test"]["status"] == expected
    assert "must-not-leak" not in str(result)


async def test_number_draft_approval_and_activation_cannot_be_forged(client, owner_headers, native_context, mock_db):
    payload = {"number": "+919000000100", "label": "Staging business number"}
    created = await client.post(f"{BASE}/numbers", headers=owner_headers, json=payload)
    assert created.status_code == 200, created.text
    number = created.json()["data"]
    assert number["state"] == "draft" and not number["live_calling"]
    assert not number["activation_eligible"]
    duplicate = await client.post(f"{BASE}/numbers", headers=owner_headers, json=payload)
    assert duplicate.status_code == 409
    forged = await client.post(f"{BASE}/numbers", headers=owner_headers, json={**payload, "number": "+919000000101", "state": "active"})
    assert forged.status_code == 422
    activated = await client.post(f"{BASE}/numbers/{number['id']}/actions", headers=owner_headers, json={"version": number["version"], "action": "activate", "reason": "test-only approval attempt"})
    assert activated.status_code == 403
    assert activated.json()["error"]["details"]["blockers"]
    assert (await mock_db.voice_phone_numbers.find_one({}))["state"] == "draft"
    assert await mock_db.voice_calls.count_documents({}) == 0


async def test_number_lifecycle_history_and_cas(native_context):
    svc, actor = native_context
    number = await svc.save_number(TelephoneNumberInput(number="+919000000102", label="Lifecycle fixture"), actor)
    reviewed = await svc.number_action(number["id"], TelephoneNumberAction(version=1, action="submit", reason="Test-only submission"), actor)
    assert reviewed["state"] == "awaiting_telecom_approval"
    with pytest.raises(ConflictError):
        await svc.number_action(number["id"], TelephoneNumberAction(version=1, action="disable", reason="Stale update attempt"), actor)
    disabled = await svc.number_action(number["id"], TelephoneNumberAction(version=reviewed["version"], action="disable", reason="Disable fixture number"), actor)
    assert disabled["state"] == "disabled" and len(disabled["timeline"]) == 2


async def test_connection_rotation_and_stale_probe_evidence(native_context, monkeypatch, mock_db):
    svc, actor = native_context
    async def passed(*args):
        return {"status": "control_probe_passed", "control_api_reachable": True, "endpoint_online": True, "media_verified": False, "calling_verified": False}
    monkeypatch.setattr(native_adapter.AsteriskReadOnlyAdapter, "probe", passed)
    item = await svc.save_connection(connection_input(), actor)
    tested = await svc.test_connection(item["id"], actor)
    number = await svc.save_number(TelephoneNumberInput(number="+919000000103", label="Fresh evidence", connection_id=item["id"], authorization_reference="operator-reference-only"), actor)
    assert number["control_evidence_fresh"] is True
    await mock_db.voice_native_connections.update_one({}, {"$set": {"last_test.checked_at": utc_now() - timedelta(minutes=16)}})
    assert (await svc.numbers(actor))["items"][0]["control_evidence_fresh"] is False
    rotated = await svc.save_connection(connection_input(version=tested["version"]), actor, item["id"])
    assert rotated["last_test"] is None
    assert (await svc.numbers(actor))["items"][0]["state"] == "verification_pending"


async def test_stale_test_cannot_overwrite_rotated_credentials(native_context, monkeypatch):
    svc, actor = native_context
    entered, release = asyncio.Event(), asyncio.Event()
    async def held(*args):
        entered.set()
        await release.wait()
        return {"status": "control_probe_passed", "control_api_reachable": True, "endpoint_online": True, "media_verified": False, "calling_verified": False}
    monkeypatch.setattr(native_adapter.AsteriskReadOnlyAdapter, "probe", held)
    item = await svc.save_connection(connection_input(), actor)
    pending = asyncio.create_task(svc.test_connection(item["id"], actor))
    await asyncio.wait_for(entered.wait(), 5)
    await svc.save_connection(connection_input(version=1), actor, item["id"])
    release.set()
    with pytest.raises(ConflictError):
        await pending
    assert (await svc.connections(actor))["items"][0]["last_test"] is None
