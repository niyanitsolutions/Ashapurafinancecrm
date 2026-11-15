import asyncio
import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError as PydanticValidationError
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.exceptions import ValidationError
from app.features.voice_assistant.airtel_auth import signed_headers
from app.features.voice_assistant.airtel_media import AirtelMediaSession
from app.features.voice_assistant.airtel_rest import (
    AirtelRequestFailure,
    AirtelRestAdapter,
    ClickToCallRequest,
)
from app.features.voice_assistant.smartflo_service import ensure_smartflo_indexes

BASE = "/api/v1/voice-assistant/airtel"
APP = "fixture-app-not-a-provider-credential"
KEY = "fixture-key-not-a-provider-credential"
CLIENT = httpx.AsyncClient


def started(account="account-1", call="call-1", stream="stream-1", **updates):
    codec = AirtelMediaSession(account_sid=account, call_sid=call)
    codec.ingest(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
    start = {
        "streamSid": stream,
        "accountSid": account,
        "callSid": call,
        "mediaFormat": {"encoding": "ulaw", "sampleRate": "8000", "channels": "1"},
        "callerNumber": "9000000001",
        "calledNumber": "9000000002",
        **updates,
    }
    codec.ingest(json.dumps({"event": "start", "streamSid": stream, "start": start}))
    return codec


def frame(event, detail, sid="stream-1"):
    return json.dumps({"event": event, "streamSid": sid, **detail})


def test_hmac_node_crypto_known_answer():
    # Independently calculated with Node crypto, not this Python implementation.
    headers = signed_headers(
        "fixture-app", "fixture-key", b"{}", at=datetime(2025, 10, 6, 12, 18, 4, tzinfo=UTC)
    )
    assert headers == {
        "Content-Type": "application/json",
        "X-Date": "Mon, 06 Oct 2025 12:18:04 GMT",
        "Digest": "SHA-256=RBNvo1WzZ4oRRq0W9+hknpT7T8If536DEMBg9hyq/4o=",
        "Authorization": 'hmac username="fixture-app", algorithm="hmac-sha256", headers="x-date digest", signature="eEkB/lgyKnmONIGdlAJDNnz4djthmvVPxK3CAx0Ju7w="',
    }
    assert (
        signed_headers("fixture-app", "fixture-key", b"{ }", at=datetime.now(UTC))["Digest"]
        != headers["Digest"]
    )


@pytest.mark.parametrize(
    "app,key", [("", KEY), (APP, ""), (APP + "\r\n", KEY), (APP, "non-ascii-\u20b9")]
)
def test_signing_rejects_invalid_credentials(app, key):
    with pytest.raises(ValueError):
        signed_headers(app, key, b"{}", at=datetime.now(UTC))


def test_protocol_audio_hold_clear_marks_and_stop():
    codec = started(customParams='{"caseId":"untrusted-reference"}')
    assert codec.ingest(json.dumps(codec.output(audio=b"\xff" * 160)))["audio"] == b"\xff" * 160
    first = codec.output(mark="speech")
    codec.output(clear=True)
    ack = codec.ingest(json.dumps(first))
    assert ack["playback"] == "clear_acknowledged" and not ack["duplicate"]
    assert codec.ingest(json.dumps(first))["duplicate"]
    second = codec.output(mark="speech")
    assert first != second
    assert codec.ingest(json.dumps(second))["playback"] == "played"
    assert codec.ingest(frame("dtmf", {"dtmf": {"digit": "#"}}))["digit"] == "#"
    codec.ingest(frame("callState", {"call": {"state": "hold"}}))
    with pytest.raises(ValidationError):
        codec.output(audio=b"\xff" * 160)
    codec.output(clear=True)
    codec.ingest(frame("callState", {"call": {"state": "unhold"}}))
    assert codec.terminate(3, "Human assistance", "+919000000003")["reason"]["code"] == 3
    with pytest.raises(ValidationError):
        codec.output(audio=b"\xff" * 160)
    assert codec.ingest(
        frame("stop", {"stop": {"accountSid": "account-1", "callSid": "call-1"}})
    ) == {"event": "stop"}
    with pytest.raises(ValidationError):
        codec.output(clear=True)


@pytest.mark.parametrize(
    "message",
    [
        "[]",
        "invalid",
        '{"event":"connected","protocol":"Call","version":"1.0.0"}',
        frame("media", {"media": {"payload": base64.b64encode(b"x" * 161).decode()}}),
        frame("media", {"media": {"payload": "!" * 216}}),
        frame(
            "media", {"media": {"payload": base64.b64encode(b"x" * 160).decode()}}, "other-stream"
        ),
        frame("mark", {"mark": {"name": "unknown"}}),
        frame("dtmf", {"dtmf": {"digit": "10"}}),
        frame("callState", {"call": {"state": []}}),
        frame("stop", {"stop": {"accountSid": "other", "callSid": "call-1"}}),
        frame("clear", {}),
    ],
)
def test_invalid_frames_fail_closed(message):
    with pytest.raises(ValidationError):
        started().ingest(message)


@pytest.mark.parametrize(
    "updates",
    [
        {"accountSid": "other"},
        {"callSid": "other"},
        {"mediaFormat": {"encoding": [], "sampleRate": "8000", "channels": "1"}},
        {"mediaFormat": {"encoding": "ulaw", "sampleRate": True, "channels": "1"}},
        {"customParams": "{}", "customParameters": '{"caseId":"other"}'},
        {"customParams": {}},
    ],
)
def test_bad_start_never_binds_identity(updates):
    with pytest.raises(ValidationError):
        started(**updates)


def test_marks_are_bounded_and_calls_do_not_share_state():
    one, two = started(), started(call="other-call", stream="other-stream")
    for _ in range(256):
        one.output(mark="label")
    with pytest.raises(ValidationError):
        one.output(mark="label")
    assert not two.marks and two.call_sid == "other-call"
    one.output(clear=True)
    assert not two.termination_requested
    assert two.output(audio=b"\xff" * 160)["streamSid"] == "other-stream"


@pytest.mark.parametrize("count", [1, 10, 50, 100, 250, 500])
def test_progressive_codec_isolation_only(count):
    codecs = [
        started(account=f"account-{i}", call=f"call-{i}", stream=f"stream-{i}")
        for i in range(count)
    ]
    for i, codec in enumerate(codecs):
        audio = bytes([i % 256]) * 160
        assert codec.ingest(json.dumps(codec.output(audio=audio)))["audio"] == audio
        assert codec.call_sid == f"call-{i}"
    # Synthetic object isolation is not concurrent network/model/telephony capacity.
    codecs[0].terminate(1, "test")
    assert all(not codec.termination_requested for codec in codecs[1:])


@pytest.mark.parametrize("retry", [True, -1, 4, {"count": 4, "status": []}])
def test_c2c_retry_validation(retry):
    with pytest.raises(PydanticValidationError):
        ClickToCallRequest.model_validate(
            {
                "from": "9000000001",
                "to": ["9000000002"],
                "caller_id": "9000000003",
                "call_flow_id": "test",
                "retry": retry,
            }
        )


async def test_rest_signs_exact_body_and_never_retries(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/gateway/airtel-xchange/v2/adv/ob-click-to-call"
        at = datetime.strptime(request.headers["X-Date"], "%a, %d %b %Y %H:%M:%S GMT").replace(
            tzinfo=UTC
        )
        assert (
            request.headers["Authorization"]
            == signed_headers(APP, KEY, request.content, at=at)["Authorization"]
        )
        return httpx.Response(200, json={"unspecifiedProviderEnvelope": True})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    payload = ClickToCallRequest.model_validate(
        {
            "from": "9000000001",
            "to": ["9000000002"],
            "caller_id": "9000000003",
            "call_flow_id": "test",
        }
    )
    status, body = await AirtelRestAdapter(APP, KEY, c2c_origin_confirmed=True).click_to_call(
        payload
    )
    assert status == 200 and json.loads(body) == {"unspecifiedProviderEnvelope": True}
    assert len(requests) == 1 and json.loads(requests[0].content)["from"] == "9000000001"


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
async def test_rest_failures_redacted_without_redirect_or_retry(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://unsafe.example.test"},
            text="sensitive-provider-body",
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(AirtelRequestFailure) as exc:
        await AirtelRestAdapter(APP, KEY).recording("private-token")
    assert (
        len(calls) == 1
        and "private-token" not in str(exc.value)
        and "sensitive" not in str(exc.value)
    )


async def test_config_owner_only_encrypted_cas_and_offline_evidence(
    client, owner_headers, employee_headers, mock_db
):
    await ensure_smartflo_indexes(mock_db)
    assert (await client.get(f"{BASE}/connection", headers=employee_headers)).status_code == 403
    assert (await client.post(f"{BASE}/tests/local", headers=employee_headers)).status_code == 403
    payload = {
        "version": 1,
        "public_origin": "https://crm.example.test",
        "app_id": APP,
        "api_key": KEY,
        "requested_concurrency": 500,
    }
    response = await client.put(f"{BASE}/connection", headers=owner_headers, json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert saved["credentials_configured"] and saved["version"] == 2
    assert not saved["live_calling"] and saved["capacity_status"] == "not_measured"
    assert APP not in response.text and KEY not in response.text
    assert saved["media_url"] == "wss://crm.example.test/api/v1/voice-assistant/airtel/media"
    stored = await mock_db.voice_provider_connections.find_one({"provider": "airtel_iq_voice"})
    assert APP not in str(stored) and KEY not in str(stored)
    assert (
        await client.put(f"{BASE}/connection", headers=owner_headers, json=payload)
    ).status_code == 409
    result = await client.post(f"{BASE}/tests/local", headers=owner_headers)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["provider_verified"] is False
    assert result.json()["data"]["calls_placed"] == 0
    response = await client.put(
        f"{BASE}/connection", headers=owner_headers, json={"version": 2, "clear_credentials": True}
    )
    assert response.status_code == 200 and not response.json()["data"]["credentials_configured"]
    assert response.json()["data"]["last_test"] is None
    assert (await client.post(f"{BASE}/tests/local", headers=owner_headers)).status_code == 422
    assert APP not in str(await mock_db.audit_logs.find({}).to_list(100))


@pytest.mark.parametrize(
    "payload",
    [
        {"live_calling": True},
        {"api_origin": "https://attacker.test"},
        {"public_origin": "http://crm.example.test"},
        {"app_id": APP},
        {"app_id": APP, "api_key": KEY + "\n"},
        {"requested_concurrency": 501},
    ],
)
async def test_config_rejects_unsafe_or_unsupported_values(client, owner_headers, payload):
    assert (
        await client.put(f"{BASE}/connection", headers=owner_headers, json=payload)
    ).status_code == 422


async def test_callbacks_remain_disabled(client):
    for route in ("events", "cdr"):
        assert (await client.post(f"{BASE}/webhooks/{route}", json={})).status_code == 403


def test_websocket_cannot_accept_live_audio():
    from app.main import create_app

    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"{BASE}/media"):
        pytest.fail("Live media must remain unavailable.")


@pytest.mark.parametrize("count", [1, 10, 50, 100, 250, 500])
async def test_progressive_concurrent_dynamic_core_with_fake_services(count):
    from app.features.voice_assistant.dynamic_audio import DynamicAudioConversation

    ready, release = 0, asyncio.Event()
    engines, outputs = [], []

    class Model:
        async def respond(self, **kwargs):
            nonlocal ready
            ready += 1
            if ready == count:
                release.set()
            await release.wait()  # All synthetic sessions overlap in model work.
            return {
                "response": kwargs["sources"][0]["excerpt"],
                "source_ids": [kwargs["sources"][0]["id"]],
                "intent": {
                    "intent": "product_information",
                    "confidence": 0.99,
                    "proposed_action": "answer_public_knowledge",
                },
                "uncertain": False,
            }

    class Speech:
        async def synthesize(self, text, language):
            await asyncio.sleep(0)
            yield b"\xff" * 160

    async def authorize():
        return True  # Fake authorization, not a trusted provider/customer identity.

    async def build(index):
        out = []

        async def retrieve(question, language):
            return [
                {
                    "id": f"source-{index}",
                    "excerpt": f"Reviewed public excerpt for fixture {index}.",
                }
            ]

        async def send(event):
            out.append(event)

        engine = DynamicAudioConversation(
            model=Model(),
            speech=Speech(),
            codec=started(call=f"call-{index}", stream=f"stream-{index}"),
            retrieve=retrieve,
            send=send,
            instructions="Use current knowledge",
            operational_rules="No promises",
            authorize=authorize,
        )
        engines.append(engine)
        outputs.append(out)
        await engine.question(f"General product information for fixture {index}?")
        await engine.drain()

    try:
        await asyncio.wait_for(asyncio.gather(*(build(i) for i in range(count))), 20)
        assert ready == count
        for i, engine in enumerate(engines):
            assert engine.history[0]["content"] == f"General product information for fixture {i}?"
            assert engine.history[1]["content"] == f"Reviewed public excerpt for fixture {i}."
            assert sum(event["event"] == "media" for event in outputs[i]) == 1
            assert all(event["streamSid"] == f"stream-{i}" for event in outputs[i])
    finally:
        await asyncio.gather(*(engine.close() for engine in engines))


async def test_mock_actions_and_worker_cannot_control_future_airtel_records(
    client, owner_headers, mock_db
):
    from datetime import timedelta

    from bson import ObjectId

    from app.features.voice_assistant.service import VoiceService
    from app.utils.datetime import utc_now

    settings = (await client.get("/api/v1/voice-assistant/settings", headers=owner_headers)).json()[
        "data"
    ]
    settings["mode"] = "mock"
    assert (
        await client.put("/api/v1/voice-assistant/settings", headers=owner_headers, json=settings)
    ).status_code == 200
    response = await client.post(
        "/api/v1/voice-assistant/mock/calls",
        headers=owner_headers,
        json={
            "direction": "incoming",
            "contact_label": "Synthetic",
            "idempotency_key": "airtel-isolation-fixture",
        },
    )
    assert response.status_code == 200, response.text
    call = response.json()["data"]
    await mock_db.voice_calls.update_one(
        {"_id": ObjectId(call["id"])},
        {"$set": {"provider": "airtel_iq_voice", "deadline_at": utc_now() - timedelta(seconds=10)}},
    )
    action = await client.post(
        f"/api/v1/voice-assistant/mock/calls/{call['id']}/actions",
        headers=owner_headers,
        json={"version": call["version"], "action": "end"},
    )
    assert action.status_code == 403
    assert await VoiceService(mock_db).sweep() == 0
    stored = await mock_db.voice_calls.find_one({"_id": ObjectId(call["id"])})
    assert stored["status"] == call["status"] and stored["version"] == call["version"]


def test_g711_exhaustive_against_independent_stdlib_reference():
    import struct

    audioop = pytest.importorskip("audioop")  # Test oracle only; runtime has no audioop dependency.
    from app.features.voice_assistant.g711 import decode_mulaw_frame, encode_pcm16_frame

    for start in range(-32768, 32768, 160):
        values = list(range(start, min(start + 160, 32768)))
        values += [0] * (160 - len(values))
        pcm = struct.pack("<160h", *values)
        assert encode_pcm16_frame(pcm) == audioop.lin2ulaw(pcm, 2)
    for code in range(256):
        encoded = bytes([code]) * 160
        assert decode_mulaw_frame(encoded) == audioop.ulaw2lin(encoded, 2)
    assert decode_mulaw_frame(b"\xff" * 160) == b"\0" * 320
    for invalid in (b"", b"x" * 159, b"RIFF" + b"x" * 160):
        with pytest.raises(ValueError):
            decode_mulaw_frame(invalid)
    with pytest.raises(ValueError):
        encode_pcm16_frame(b"x" * 319)


async def test_c2c_does_not_send_without_confirmed_origin(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("Unconfirmed C2C origin must not reach the network.")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    payload = ClickToCallRequest.model_validate(
        {"from": 9000000001, "to": [9000000002], "caller_id": "9000000003", "call_flow_id": "test"}
    )
    assert payload.from_number == "9000000001" and payload.to == ["9000000002"]
    with pytest.raises(AirtelRequestFailure):
        await AirtelRestAdapter(APP, KEY).click_to_call(payload)


async def test_recording_exact_path_empty_body_signature_and_bounds(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/gateway/airtel-xchange/callv2/recording"
        assert request.url.params["token"] == "opaque-token"
        assert request.content == b""
        return httpx.Response(200, content=b"example-binary-not-a-validated-recording")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert (
        await AirtelRestAdapter(APP, KEY).recording("opaque-token")
        == b"example-binary-not-a-validated-recording"
    )
    assert len(requests) == 1


async def test_oversized_provider_response_is_rejected(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"x" * 65537)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    from app.features.voice_assistant.airtel_rest import C2C_PATH

    with pytest.raises(AirtelRequestFailure):
        await AirtelRestAdapter(APP, KEY, c2c_origin_confirmed=True).request(
            "POST", C2C_PATH, body=b"{}"
        )


async def test_dependency_logs_cannot_expose_recording_token(monkeypatch, caplog):
    import logging

    def handler(request):
        logging.getLogger("httpcore.http11").debug("headers %s", KEY)
        return httpx.Response(200, content=b"binary")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    with caplog.at_level(logging.DEBUG):
        await AirtelRestAdapter(APP, KEY).recording("private-token-must-never-be-logged")
        logging.getLogger("httpx").info("unrelated CRM request remains visible")
    assert "private-token-must-never-be-logged" not in caplog.text and KEY not in caplog.text
    assert "unrelated CRM request remains visible" in caplog.text


async def test_private_logging_context_is_task_scoped_and_resets_on_error(caplog):
    import logging

    from app.features.voice_assistant.airtel_logging import private_transport_logs

    async def private():
        with pytest.raises(ValueError), private_transport_logs():
            await asyncio.sleep(0)
            logging.getLogger("httpx").info("private-must-be-hidden")
            raise ValueError("fixture")
        logging.getLogger("httpx").info("context-was-reset")

    async def unrelated():
        logging.getLogger("httpx").info("concurrent-request-is-visible")

    with caplog.at_level(logging.INFO):
        await asyncio.gather(private(), unrelated())
    assert "private-must-be-hidden" not in caplog.text
    assert "context-was-reset" in caplog.text and "concurrent-request-is-visible" in caplog.text
