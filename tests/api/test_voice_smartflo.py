import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.features.voice_assistant.smartflo_config import API_ORIGIN
from app.features.voice_assistant.smartflo_media import SmartfloMediaSession
from app.features.voice_assistant.smartflo_service import ensure_smartflo_indexes
from app.utils.datetime import utc_now

BASE = "/api/v1/voice-assistant/smartflo"
API_TOKEN = "test-only-api-token-with-no-provider-access"
CALLBACK_TOKEN = "separate-test-only-callback-token-1234567890"
ORIGINAL_HTTP_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
async def indexes(mock_db):
    await ensure_smartflo_indexes(mock_db)


async def save(client, owner_headers, **updates):
    status = (await client.get(f"{BASE}/connection", headers=owner_headers)).json()["data"]
    payload = {
        "version": status["version"],
        "public_origin": "https://crm.example.test",
        "api_token": API_TOKEN,
        "callback_token": CALLBACK_TOKEN,
        **updates,
    }
    response = await client.put(f"{BASE}/connection", headers=owner_headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def mock_provider(monkeypatch, handler):
    original = ORIGINAL_HTTP_CLIENT
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )


async def test_connection_permissions_and_secret_redaction(
    client, owner_headers, employee_headers, mock_db
):
    for path in ("connection", "events"):
        assert (await client.get(f"{BASE}/{path}", headers=employee_headers)).status_code == 403
    for kind in ("connection", "webhook", "audio"):
        assert (
            await client.post(f"{BASE}/tests/{kind}", headers=employee_headers)
        ).status_code == 403
    assert (await client.post(f"{BASE}/tests/connection", headers=owner_headers)).status_code == 422
    result = await save(client, owner_headers)
    assert result["api_token_configured"] and result["callback_token_configured"]
    assert API_TOKEN not in json.dumps(result) and CALLBACK_TOKEN not in json.dumps(result)
    doc = await mock_db.voice_provider_connections.find_one({"provider": "smartflo"})
    assert doc["api_token_encrypted"] != API_TOKEN
    assert doc["callback_token_encrypted"] != CALLBACK_TOKEN
    assert "api_token" not in doc
    audits = await mock_db.audit_logs.find({"event_type": {"$regex": "smartflo"}}).to_list(100)
    assert API_TOKEN not in str(audits) and CALLBACK_TOKEN not in str(audits)


async def test_urls_and_configuration_reject_unsafe_changes(client, owner_headers):
    for payload in (
        {"api_base_url": "https://attacker.example"},
        {"public_origin": "http://crm.example"},
        {"public_origin": "https://user:pass@crm.example"},
        {"public_origin": "https://crm.example/path"},
        {"api_token": API_TOKEN + "\n"},
        {"token_expires_at": "2026-12-01T12:00:00"},
        {"live_calling": True},
        {"callback_mode": "live"},
    ):
        response = await client.put(f"{BASE}/connection", headers=owner_headers, json=payload)
        assert response.status_code == 422, response.text
    status = await save(client, owner_headers)
    assert status["api_base_url"] == API_ORIGIN
    assert status["incoming_webhook_url"].endswith("/smartflo/webhooks/incoming")
    assert status["audio_websocket_url"].startswith("wss://")
    assert status["live_calling"] is False
    assert (
        await client.put(f"{BASE}/connection", headers=owner_headers, json={"version": 1})
    ).status_code == 409
    assert (
        await client.put(
            f"{BASE}/connection",
            headers=owner_headers,
            json={
                "version": status["version"],
                "api_token": CALLBACK_TOKEN,
                "callback_token": CALLBACK_TOKEN,
            },
        )
    ).status_code == 422


async def test_readonly_probe_and_invalidation(client, owner_headers, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == "/v1/users"
        assert request.url.params["limit"] == "1"
        assert request.headers["Authorization"] == f"Bearer {API_TOKEN}"
        return httpx.Response(200, json={"data": [{"name": "Private provider user"}]})

    await save(client, owner_headers)
    mock_provider(monkeypatch, handler)
    response = await client.post(f"{BASE}/tests/connection", headers=owner_headers)
    assert response.json()["data"]["status"] == "readonly_verified"
    assert "Private provider user" not in response.text
    assert len(requests) == 1
    result = await save(client, owner_headers)
    assert result["last_test"] is None and result["connection_status"] == "not_tested"


@pytest.mark.parametrize("code", [401, 403, 429, 500, 302])
async def test_provider_errors_do_not_leak_or_retry(client, owner_headers, monkeypatch, code):
    await save(client, owner_headers)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            code, json={"message": API_TOKEN}, headers={"location": "https://attacker.example"}
        )

    mock_provider(monkeypatch, handler)
    response = await client.post(f"{BASE}/tests/connection", headers=owner_headers)
    assert response.status_code == 200 and response.json()["data"]["status"] == "failed"
    assert API_TOKEN not in response.text and len(requests) == 1


async def test_invalid_json_and_timeout_fail_closed(client, owner_headers, monkeypatch):
    await save(client, owner_headers)
    mock_provider(monkeypatch, lambda request: httpx.Response(200, text="invalid JSON"))
    assert (await client.post(f"{BASE}/tests/connection", headers=owner_headers)).json()["data"][
        "status"
    ] == "failed"

    def timeout(request):
        raise httpx.ReadTimeout("do not echo sensitive upstream details", request=request)

    mock_provider(monkeypatch, timeout)
    result = await client.post(f"{BASE}/tests/connection", headers=owner_headers)
    assert result.json()["data"]["status"] == "failed"
    assert "sensitive upstream" not in result.text


async def test_expired_token_prevents_network_probe(client, owner_headers, monkeypatch):
    await save(
        client, owner_headers, token_expires_at=(utc_now() - timedelta(seconds=1)).isoformat()
    )

    def unexpected(request):
        pytest.fail("Expired token must not be sent upstream.")

    mock_provider(monkeypatch, unexpected)
    assert (await client.post(f"{BASE}/tests/connection", headers=owner_headers)).status_code == 422


async def test_oversized_api_response_is_not_retained(client, owner_headers, monkeypatch):
    await save(client, owner_headers)
    mock_provider(
        monkeypatch, lambda request: httpx.Response(200, json={"data": [{"name": "x" * 70000}]})
    )
    response = await client.post(f"{BASE}/tests/connection", headers=owner_headers)
    assert response.json()["data"]["status"] == "failed"
    assert "oversized" in response.json()["data"]["message"]
    assert len(response.content) < 1000


async def test_authenticated_callback_duplicate_order_and_minimization(
    client, owner_headers, mock_db
):
    stamp = utc_now().isoformat()
    payload = {"uuid": "test-provider-call", "start_stamp": stamp}
    assert (await client.post(f"{BASE}/webhooks/incoming", json=payload)).status_code == 401
    await save(client, owner_headers)
    headers = {"Authorization": f"Bearer {CALLBACK_TOKEN}"}
    assert (
        await client.post(f"{BASE}/webhooks/incoming", headers=headers, json=payload)
    ).status_code == 403
    await save(client, owner_headers, callback_mode="validation_only")
    first = await client.post(f"{BASE}/webhooks/incoming", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert not first.json()["data"]["duplicate"]
    again = await client.post(f"{BASE}/webhooks/incoming", headers=headers, json=payload)
    assert again.json()["data"]["duplicate"]
    hangup = {**payload, "call_status": "Answered"}
    assert (
        await client.post(f"{BASE}/webhooks/hangup", headers=headers, json=hangup)
    ).status_code == 200
    assert await mock_db.voice_provider_events.count_documents({}) == 2
    assert await mock_db.voice_calls.count_documents({}) == 0
    assert (
        await client.post(
            f"{BASE}/webhooks/incoming", headers=headers, json={**payload, "api_token": API_TOKEN}
        )
    ).status_code == 422
    doc = await mock_db.voice_provider_events.find_one({})
    assert "raw_payload" not in doc and "recording_url" not in doc
    assert doc["expires_at"] - doc["received_at"] == timedelta(days=30)
    assert (
        await client.post(
            f"{BASE}/webhooks/incoming",
            headers={**headers, "Content-Type": "application/json"},
            content="x" * 17000,
        )
    ).status_code == 422
    assert (await client.post(f"{BASE}/stream/resolve", headers=headers)).status_code == 403


async def test_local_tests_do_not_claim_provider_verification(client, owner_headers):
    await save(client, owner_headers)
    webhook = (await client.post(f"{BASE}/tests/webhook", headers=owner_headers)).json()["data"]
    assert webhook["status"] == "local_persistence_passed"
    audio = (await client.post(f"{BASE}/tests/audio", headers=owner_headers)).json()["data"]
    assert audio["status"] == "offline_protocol_passed" and not audio["live_stream_verified"]
    logs = (await client.get(f"{BASE}/events", headers=owner_headers)).json()["data"]
    assert logs["items"][0]["status"] == "test_observation"


def active_codec():
    codec = SmartfloMediaSession("test-account", "test-call")
    codec.ingest('{"event":"connected"}')
    start = {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": "test-stream",
        "start": {
            "accountSid": "test-account",
            "callSid": "test-call",
            "streamSid": "test-stream",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "bitRate": 64,
                "bitDepth": 8,
            },
        },
    }
    codec.ingest(json.dumps(start))
    return codec


def test_audio_identity_replay_stop_and_format():
    from app.core.exceptions import ValidationError

    codec = active_codec()
    assert codec.output(audio=bytes([255]) * 160)["media"]["chunk"] == 1
    assert codec.output(clear=True)["event"] == "clear"
    with pytest.raises(ValidationError):
        codec.output(audio=b"short")
    event = {
        "event": "media",
        "sequenceNumber": "2",
        "streamSid": "other-stream",
        "media": {"payload": "////"},
    }
    with pytest.raises(ValidationError):
        codec.ingest(json.dumps(event))
    event["streamSid"] = "test-stream"
    assert codec.ingest(json.dumps(event))["audio"]
    with pytest.raises(ValidationError):
        codec.ingest(json.dumps(event))
    codec.ingest(
        json.dumps(
            {
                "event": "stop",
                "sequenceNumber": "3",
                "streamSid": "test-stream",
                "stop": {"accountSid": "test-account", "callSid": "test-call"},
            }
        )
    )
    with pytest.raises(ValidationError):
        codec.output(clear=True)


def test_live_websocket_rejected():
    from app.main import create_app

    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"{BASE}/media"):
        pytest.fail("Live media must remain disabled.")


async def test_dynamic_voice_context_and_interruption():
    from app.features.voice_assistant.dynamic_audio import DynamicAudioConversation

    async def authorize():
        return True  # Synthetic host session; no telephone identity is asserted.

    captured = []
    sent = []
    started = asyncio.Event()
    wait = asyncio.Event()

    class Model:
        async def respond(self, **kwargs):
            captured.append(kwargs)
            return {
                "response": kwargs["sources"][0]["excerpt"],
                "intent": {"intent": "product_information", "confidence": 0.95, "proposed_action": "answer_public_knowledge"},
                "source_ids": ["approved"],
                "uncertain": False,
            }

    class Speech:
        async def synthesize(self, text, language):
            started.set()
            if len(captured) == 1:
                await wait.wait()
            yield bytes([255]) * 160

    async def retrieve(question, language):
        return [{"id": "approved", "excerpt": "Current approved policy"}]

    async def send(event):
        sent.append(event)

    engine = DynamicAudioConversation(
        model=Model(),
        speech=Speech(),
        codec=active_codec(),
        retrieve=retrieve,
        send=send,
        instructions="Be helpful.",
        operational_rules="No guarantees.",
        authorize=authorize,
    )
    await engine.question("An unusual question about my situation")
    await asyncio.wait_for(started.wait(), 1)
    await engine.question("And what documents would apply?")
    await engine.drain()
    assert captured[1]["question"] == "And what documents would apply?"
    assert "untrusted data" in captured[1]["instructions"]
    assert captured[1]["history"][0]["content"] == "An unusual question about my situation"
    assert sum(event["event"] == "clear" for event in sent) == 2
    assert sum(event["event"] == "media" for event in sent) == 1
    await engine.close()


async def test_connection_test_cannot_verify_replaced_credentials(
    client, owner_headers, mock_db, monkeypatch
):
    await save(client, owner_headers)

    async def handler(request):
        await mock_db.voice_provider_connections.update_one(
            {"provider": "smartflo"}, {"$inc": {"version": 1}}
        )
        return httpx.Response(200, json={"data": []})

    mock_provider(monkeypatch, handler)
    assert (await client.post(f"{BASE}/tests/connection", headers=owner_headers)).status_code == 409
    doc = await mock_db.voice_provider_connections.find_one({"provider": "smartflo"})
    assert doc["last_test"] is None


async def test_event_duplicates_are_atomic_and_expired_events_hidden(
    client, owner_headers, mock_db
):
    from app.features.voice_assistant.smartflo_config import SmartfloWebhookInput
    from app.features.voice_assistant.smartflo_service import SmartfloService

    service = SmartfloService(mock_db)
    payload = SmartfloWebhookInput(uuid="concurrent-test", start_stamp=utc_now())
    results = await asyncio.gather(
        *(service.ingest("incoming", payload, test=True) for _ in range(8))
    )
    assert sum(not result["duplicate"] for result in results) == 1
    await mock_db.voice_provider_events.update_one(
        {}, {"$set": {"expires_at": utc_now() - timedelta(seconds=1)}}
    )
    assert (await client.get(f"{BASE}/events", headers=owner_headers)).json()["data"]["total"] == 0


async def test_invalid_stored_credentials_allow_deactivation_and_clear_errors(client, owner_headers, mock_db):
    config = await save(client, owner_headers)
    await mock_db.voice_provider_connections.update_one({"provider": "smartflo"}, {"$set": {"callback_token_encrypted": "invalid-ciphertext"}})
    result = await client.post(f"{BASE}/tests/webhook", headers=owner_headers)
    assert result.status_code == 422 and "cannot be decrypted" in result.text
    response = await client.put(f"{BASE}/connection", headers=owner_headers, json={"version": config["version"], "callback_mode": "disabled"})
    assert response.status_code == 200


async def test_dynamic_audio_hangup_and_turn_limits():
    from app.features.voice_assistant.dynamic_audio import DynamicAudioConversation

    captured = []

    class Model:
        async def respond(self, **kwargs):
            return {"response": "Please clarify the service.", "source_ids": [], "uncertain": True}

    class Speech:
        async def synthesize(self, text, language):
            yield bytes([255]) * 160

    async def retrieve(question, language):
        return []

    async def send(event):
        captured.append(event)

    codec = active_codec()
    engine = DynamicAudioConversation(
        model=Model(),
        speech=Speech(),
        codec=codec,
        retrieve=retrieve,
        send=send,
        instructions="Be helpful.",
        operational_rules="Escalate uncertainty.",
        max_turns=1,
    )
    await engine.question("Can you guarantee approval?")
    await engine.drain()
    assert engine.escalation_required
    await engine.question("Another question")
    assert engine.closed and engine.turns == 1
    codec = active_codec()
    engine = DynamicAudioConversation(
        model=Model(),
        speech=Speech(),
        codec=codec,
        retrieve=retrieve,
        send=send,
        instructions="Be helpful.",
        operational_rules="Escalate uncertainty.",
    )
    codec.ingest(
        json.dumps(
            {
                "event": "stop",
                "sequenceNumber": "2",
                "streamSid": "test-stream",
                "stop": {"accountSid": "test-account", "callSid": "test-call"},
            }
        )
    )
    await engine.close()
    assert engine.closed
